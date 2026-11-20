"""Retour du testeur du 17/11/2026 : Irlande, minute du temps additionnel, montante terminée,
écart moteur - cote des sélections nationales dans la Fiabilité."""

from datetime import UTC, date, datetime, timedelta
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono.bookmaker import settlement
from footprono.bookmaker.montante_models import Montante
from footprono.football.models import Match, Team
from footprono.ingestion.nations import NATION_COUNTRY, rename_nations
from footprono.notifications.models import Notification
from footprono.predictions import reliability

from .conftest import make_premium
from .test_bets import _login, _sel, world  # noqa: F401 (fixture partagée)

Factory = async_sessionmaker[AsyncSession]


async def test_rep_of_ireland_becomes_irlande(db_factory: Factory) -> None:
    async with db_factory() as session:
        session.add(Team(name="Rep. Of Ireland", country=NATION_COUNTRY))
        await session.flush()
        assert await rename_nations(session) == 1
        names = set((await session.scalars(select(Team.name))).all())
    assert "Irlande" in names
    assert "Rep. Of Ireland" not in names


async def test_goal_in_added_time_shows_90_plus(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
    db_factory: Factory,
) -> None:
    """Burkina Faso - Mauritanie, 13/11/2026 : « 90' » pour un but de la 90+4e."""
    m1 = world["m1"]
    headers = await _login(client)
    r = await client.post(
        "/api/v1/bets", json={"stake": 1000, "selections": [_sel(m1, "1X2", "home")]},
        headers=headers,
    )  # fmt: skip
    assert r.status_code == 201, r.text
    now = datetime.now(UTC)
    live = {"kickoff_at": now - timedelta(minutes=100), "api_status": "2H", "live_updated_at": now}
    async with db_factory() as session:
        await session.execute(
            update(Match).where(Match.id == m1).values(
                **live, live_minute=88, live_extra=None, live_home_goals=0, live_away_goals=0
            )
        )  # fmt: skip
        await session.commit()
        await settlement.settle_bets(session, now)  # nul pour l'instant : perdante
        await session.execute(
            update(Match).where(Match.id == m1).values(
                live_minute=90, live_extra=4, live_home_goals=1, live_away_goals=0
            )
        )  # fmt: skip
        await session.commit()
        await settlement.settle_bets(session, now)
        notes = (
            await session.scalars(select(Notification).where(Notification.kind == "bet_live"))
        ).all()
    assert any("⚽ 90+4' " in n.body for n in notes), [n.body for n in notes]


async def test_finished_montante_gets_a_clear_error(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
    db_factory: Factory,
) -> None:
    """Montante n° 8 du 14/11/2026 : perdue, et encore 3 suggestions."""
    headers = await _login(client)
    await make_premium(db_factory, "+22997111111")
    mid = (
        await client.post(
            "/api/v1/montantes",
            json={"start_stake": 5000, "steps": [{"odds_min": "1.80", "odds_max": "1.90"}] * 4},
            headers=headers,
        )
    ).json()["id"]
    async with db_factory() as session:
        await session.execute(update(Montante).where(Montante.id == mid).values(status="lost"))
        await session.commit()
    r = await client.get(f"/api/v1/montantes/{mid}/suggestions", headers=headers)
    assert r.status_code == 400
    body = r.json()["error"]
    assert body["details"] == {"code": "montante_finished", "status": "lost"}
    assert "nouvelle montante" in body["message"]


class _Rows:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self.rows = rows

    def all(self) -> list[tuple[Any, ...]]:
        return self.rows


class _Session:
    """Cotes d'avant-match simulées (1xBet) pour deux matchs de sélections."""

    async def execute(self, *_a: Any, **_k: Any) -> _Rows:
        mw, dc = "Match Winner", "Double Chance"
        return _Rows(
            [
                (m, "1xBet", mw, v, p)
                for m in (1, 2)
                for v, p in (("Home", 1.80), ("Draw", 3.60), ("Away", 4.50))
            ]
            + [
                (m, "1xBet", dc, v, p)
                for m in (1, 2)
                for v, p in (("Home/Draw", 1.30), ("Draw/Away", 2.10), ("Home/Away", 1.25))
            ]
        )


async def test_nations_engine_versus_odds_in_reliability() -> None:
    """Israël - Autriche, 74 % contre 56 % : ces écarts tiennent-ils ?"""
    code = next(iter(reliability.NATIONS_BY_CODE))

    def row(mid: int, home_won: bool) -> reliability.Scored:
        return reliability.Scored(
            match_id=mid, match_date=date(2026, 11, 15), competition=code, home="A", away="B",
            score=(1, 0) if home_won else (0, 1), engine_version="test",
            probs={"1X2": (0.70, 0.18, 0.12)},
            outcome={"1X2": 0 if home_won else 2},
        )  # fmt: skip

    league = reliability.Scored(
        match_id=3, match_date=date(2026, 11, 15), competition="EPL", home="C", away="D",
        score=(1, 0), engine_version="test", probs={"1X2": (0.7, 0.2, 0.1)}, outcome={"1X2": 0},
    )  # fmt: skip
    out = await reliability.nations_vs_odds(
        _Session(),  # type: ignore[arg-type]
        [row(1, True), row(2, False), league],
    )
    assert out is not None
    assert out["matches"] == 2  # le championnat n'est pas compté
    top = out["bands"][2]  # 70 % contre 1 / 1,80 = 55,6 % : +14,4 points
    assert top["selections"] == 0
    middle = out["bands"][1]
    assert middle["selections"] == 2
    assert middle["engine"] == 0.7
    assert middle["implied"] == round(1 / 1.80, 4)
    assert middle["won"] == 0.5
    assert middle["profit"] == 800 - 1000  # 1 800 rendus, 2 000 misés
    # Audit du 20/11/2026 (point 3) : les autres marchés aussi. Double chance « 1X » :
    # 88 % pour le moteur contre 1 / 1,30 = 76,9 % (+11 points) ; gagnée une fois sur deux.
    dc = next(m for m in out["markets"] if m["market"] == "DC")
    assert dc["bands"][1]["selections"] == 2
    assert dc["bands"][1]["won"] == 0.5
    assert {m["market"] for m in out["markets"]} == {"1X2", "DC", "OU|2.5", "BTTS"}
    assert await reliability.nations_vs_odds(_Session(), [league]) is None  # type: ignore[arg-type]
