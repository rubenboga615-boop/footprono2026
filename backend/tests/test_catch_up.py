"""« Tout rattraper » (incident du 16/11/2026, docs/AUDIT_JEU_2026-11-16.md) : quota vide puis
revenu, une notification de synthèse, relance sans effet, pas de remboursement à tort, réserve
de la collecte d'historique."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono.bookmaker import settlement
from footprono.bookmaker.models import Bet, BetSelection
from footprono.console.jobs import JobContext
from footprono.console.registry import get_action
from footprono.core.errors import AppError
from footprono.football.models import Match, MatchStatus
from footprono.ingestion import live, service
from footprono.ingestion.sources import api_football
from footprono.notifications.models import Notification
from footprono.worker import catchup, tasks

from .conftest import make_settings
from .test_bets import NOW, _login, _sel, world  # noqa: F401 (fixture partagée)
from .test_live_follow import _fast_init, _item

Factory = async_sessionmaker[AsyncSession]
F1, F2 = 8001, 8002


def _transport(remaining: int, calls: list[str]) -> httpx.MockTransport:
    """API-Football simulée : ``remaining`` requêtes du jour ; les deux matchs terminés."""
    stats = [{"type": "Corner Kicks", "value": 5}]

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        headers = {"x-ratelimit-requests-remaining": str(remaining), "x-ratelimit-remaining": "290"}
        if request.url.path == "/status":
            body: Any = {"response": {"requests": {"current": 7500 - remaining, "limit_day": 7500}}}
        elif request.url.path == "/fixtures":
            body = {
                "response": [
                    _item(F1, "FT", 90, (2, 0), (1, 0)),
                    _item(F2, "FT", 90, (0, 1), (0, 0)),
                ]
            }
        else:
            body = {
                "response": [
                    {"team": {"id": t}, "statistics": stats, "statistics_1h": stats,
                     "statistics_2h": stats}
                    for t in (1, 2)
                ]
            }  # fmt: skip
        return httpx.Response(200, json={**body, "errors": []}, headers=headers)

    return httpx.MockTransport(handler)


async def _stub(*_a: Any, **_k: Any) -> dict[str, Any]:
    return {"status": "skipped"}


async def test_quota_out_then_back_settles_with_one_summary_and_is_idempotent(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
    db_factory: Factory,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    m1, m2 = world["m1"], world["m2"]
    headers = await _login(client)
    for sel in (_sel(m1, "1X2", "home"), _sel(m2, "1X2", "home"), _sel(m2, "1X2", "away")):
        r = await client.post(
            "/api/v1/bets", json={"stake": 1000, "selections": [sel]}, headers=headers
        )
        assert r.status_code == 201, r.text
    # Les matchs ont eu lieu hier ; le suivi n'a rien pu demander (quota vide).
    async with db_factory() as session:
        for mid, fid in ((m1, F1), (m2, F2)):
            await session.execute(
                update(Match)
                .where(Match.id == mid)
                .values(api_football_id=fid, kickoff_at=NOW - timedelta(days=1))
            )
        await session.commit()
    monkeypatch.setattr(api_football.ApiFootballClient, "__init__", _fast_init)
    for name in ("_collect_odds", "_predict_upcoming", "_warm_reliability", "_engine_chances"):
        monkeypatch.setattr(tasks, name, _stub)
    settings = make_settings(raw_data_dir=tmp_path / "raw", api_football_key="k" * 32)

    # 1. Quota presque vide : le direct s'arrête et le dit ; rien n'est réglé ni remboursé.
    calls: list[str] = []
    monkeypatch.setattr(service, "api_football_transport", _transport(150, calls))
    async with db_factory() as session:
        stopped = await live.follow_live(session, settings, catch_up=True)
    assert stopped["status"] == live.QUOTA_STOPPED
    assert calls == ["/status"]
    async with db_factory() as session:
        pending = await settlement.settle_bets(session, catch_up=True)
    assert pending["settled"] == 0

    # Le rattrapage refuse de manger la réserve du direct.
    with pytest.raises(catchup.CatchUpRefusedError, match="quota insuffisant"):
        await catchup.run(settings, db_factory)

    # 2. Quota revenu : tout est rattrapé, une seule notification de synthèse.
    monkeypatch.setattr(service, "api_football_transport", _transport(7400, calls))
    logs: list[str] = []
    report = await catchup.run(settings, db_factory, log=logs.append)
    assert any(line.startswith("Matchs en retard : 2") for line in logs)
    assert len(report["matches"]["finished"]) == 2
    assert report["settlement"]["bets"]["won"] == 2
    assert report["settlement"]["bets"]["lost"] == 1
    assert report["still_late"] == []
    async with db_factory() as session:
        notes = (
            await session.scalars(
                select(Notification).where(Notification.user_id == world["user_id"])
            )
        ).all()
        bets = (await session.scalars(select(Bet))).all()
    settled = [n for n in notes if n.kind == "bet_settled"]
    assert len(settled) == 1
    assert settled[0].title == "Résultats en retard"
    assert settled[0].body.startswith("Résultats en retard : 2 paris gagnés (+")
    assert "1 perdu" in settled[0].body
    assert settled[0].data["catch_up"] is True
    assert not [n for n in notes if n.kind == "bet_live"]  # ni but, ni coup d'envoi, ni retard
    assert {b.status for b in bets} == {"settled"}

    # 3. Relancé : rien de plus (ni règlement, ni notification).
    again = await catchup.run(settings, db_factory)
    assert again["settlement"]["bets"] == {"won": 0, "lost": 0, "push": 0, "partial": 0}
    async with db_factory() as session:
        count = len(
            (
                await session.scalars(
                    select(Notification).where(Notification.user_id == world["user_id"])
                )
            ).all()
        )
    assert count == len(notes)


async def test_never_refunded_without_the_source_confirming(
    world: dict[str, Any],  # noqa: F811
    db_factory: Factory,
) -> None:
    """Match « reporté » vu une fois, puis plus jamais redemandé (quota, panne) : pas de
    remboursement au bout de 48 h ; remboursé quand la source le confirme plus tard."""
    m1 = world["m1"]
    kickoff = NOW - timedelta(hours=60)
    async with db_factory() as session:
        await session.execute(
            update(Match)
            .where(Match.id == m1)
            .values(kickoff_at=kickoff, api_status="PST", live_updated_at=kickoff)
        )
        await session.commit()
        sel = BetSelection(
            match_id=m1, market="1X2", line="", selection="home", odds=Decimal("1.85")
        )
        assert await settlement.grade_selection(session, sel, NOW) is None
        # Jamais remis à jour, même « à venir » : jamais remboursé.
        await session.execute(
            update(Match).where(Match.id == m1).values(api_status="NS", live_updated_at=None)
        )
        await session.commit()
        assert await settlement.grade_selection(session, sel, NOW) is None
        # La source confirme le report un jour et demi après l'heure prévue : remboursé.
        await session.execute(
            update(Match)
            .where(Match.id == m1)
            .values(api_status="PST", live_updated_at=kickoff + timedelta(hours=36))
        )
        await session.commit()
        grade = await settlement.grade_selection(session, sel, NOW)
    assert grade is not None
    assert grade.result == "push"
    async with db_factory() as session:
        match = await session.get(Match, m1)
    assert match is not None
    assert match.status is MatchStatus.SCHEDULED


def test_history_collection_refuses_a_low_reserve() -> None:
    action = get_action("collect_history")
    with pytest.raises(Exception, match="au moins 1000"):
        action.validate({"reserve": 200})
    assert action.validate({})["reserve"] == 1500
    assert action.validate({})["daytime_ok"] is False


async def test_history_collection_keeps_the_live_reserve(
    world: dict[str, Any],  # noqa: F811
    db_factory: Factory,
) -> None:
    from footprono.console.actions import history_reserve_check

    # Les deux matchs de la fixture se jouent cet après-midi, et suivis en direct.
    afternoon = datetime(NOW.year, NOW.month, NOW.day, 15, tzinfo=UTC)
    async with db_factory() as session:
        for mid, fid in ((world["m1"], F1), (world["m2"], F2)):
            await session.execute(
                update(Match)
                .where(Match.id == mid)
                .values(api_football_id=fid, kickoff_at=afternoon)
            )
        await session.commit()
    ctx = JobContext(db_factory, make_settings(), 0)
    morning = afternoon - timedelta(hours=6)
    with pytest.raises(AppError, match="réserve trop basse"):
        # 2 matchs : environ 230 requêtes de direct, plus 200 gardées et 300 de marge.
        await history_reserve_check(ctx, 500, daytime_ok=True, now=morning)
    with pytest.raises(AppError, match="22 h 30"):
        await history_reserve_check(ctx, 5000, daytime_ok=False, now=morning)
    await history_reserve_check(ctx, 5000, daytime_ok=True, now=morning)  # confirmé
    evening = afternoon + timedelta(hours=8)
    await history_reserve_check(ctx, 1000, daytime_ok=False, now=evening)  # matchs finis


async def test_late_match_without_news_says_results_are_late(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
    db_factory: Factory,
) -> None:
    """16/11/2026 : « n'a pas commencé : heure à confirmer » envoyé alors que c'était le
    suivi qui était arrêté. Sans relevé récent, le joueur lit « résultats en retard »."""
    m1 = world["m1"]
    headers = await _login(client)
    r = await client.post(
        "/api/v1/bets", json={"stake": 1000, "selections": [_sel(m1, "1X2", "home")]},
        headers=headers,
    )  # fmt: skip
    assert r.status_code == 201, r.text
    now = datetime.now(UTC)
    async with db_factory() as session:
        await session.execute(
            update(Match)
            .where(Match.id == m1)
            .values(kickoff_at=now - timedelta(hours=1), api_status="NS", live_updated_at=None)
        )
        await session.commit()
        await settlement.settle_bets(session, now)
        note = (
            await session.scalars(select(Notification).where(Notification.kind == "bet_live"))
        ).one()
    assert note.title == "Résultats en retard"
    assert "ils arriveront dès que possible" in note.body
    assert "heure à confirmer" not in note.body


async def test_catch_up_lock_belongs_to_its_run() -> None:
    """Audit du 20/11/2026 (point D) : le verrou est court et prolongé à chaque étape, le
    règlement normal n'attend que pendant l'étape 2, et un verrou étranger n'est pas effacé."""
    from footprono.cache.redis import create_redis

    redis = create_redis(make_settings())
    try:
        await redis.delete(catchup.LOCK, catchup.SETTLE_LOCK)
        await redis.set(catchup.LOCK, "mon-jeton", ex=60)
        steps = catchup._Steps(redis, "mon-jeton", lambda _i: None)
        await steps(1)
        assert await redis.ttl(catchup.LOCK) > 60  # prolongé
        assert not await redis.exists(catchup.SETTLE_LOCK)
        await steps(2)
        assert await redis.get(catchup.SETTLE_LOCK) == "mon-jeton"
        await steps(3)
        assert not await redis.exists(catchup.SETTLE_LOCK)
        # Verrou repris par un autre rattrapage : ni prolongé, ni effacé.
        await redis.set(catchup.LOCK, "autre", ex=60)
        await steps(4)
        await steps.release(catchup.LOCK)
        assert await redis.get(catchup.LOCK) == "autre"
        assert await redis.ttl(catchup.LOCK) <= 60
    finally:
        await redis.delete(catchup.LOCK, catchup.SETTLE_LOCK)
        await redis.aclose()
