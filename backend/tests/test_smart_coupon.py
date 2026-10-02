"""Coupon intelligent : génération, coupons du jour, règlement, historique, marchés retirés."""

from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono.bookmaker import smart_coupon
from footprono.engine.markets import offered
from footprono.football.models import Match, MatchStatus

from .test_bets import NOW, _login, quote, world  # noqa: F401 (fixture partagée)
from .test_montante import _predict

Factory = async_sessionmaker[AsyncSession]
DAY = (NOW + timedelta(days=1)).date()
KICKOFF = datetime(DAY.year, DAY.month, DAY.day, 20, tzinfo=UTC)
MORNING = datetime(DAY.year, DAY.month, DAY.day, 8, 5, tzinfo=UTC)


async def _evening(factory: Factory, ids: list[int]) -> None:
    async with factory() as session:
        await session.execute(update(Match).where(Match.id.in_(ids)).values(kickoff_at=KICKOFF))
        await session.commit()


async def _result(factory: Factory, match_id: int, home: int, away: int) -> dict[str, int]:
    async with factory() as session:
        await session.execute(
            update(Match)
            .where(Match.id == match_id)
            .values(
                status=MatchStatus.FINISHED, home_goals=home, away_goals=away,
                result_source="api_football", api_status="FT",
            )
        )  # fmt: skip
        await session.commit()
        return await smart_coupon.settle_pending(session, KICKOFF + timedelta(hours=3))


def test_period_windows() -> None:
    friday = datetime(2026, 10, 2, 10, tzinfo=UTC)
    start, end = smart_coupon.period_window("today", friday)
    assert (start, end) == (friday + timedelta(minutes=15), datetime(2026, 10, 3, tzinfo=UTC))
    assert smart_coupon.period_window("weekend", friday) == (
        datetime(2026, 10, 3, tzinfo=UTC),
        datetime(2026, 10, 5, tzinfo=UTC),
    )
    sunday = datetime(2026, 10, 4, 12, tzinfo=UTC)
    assert smart_coupon.period_window("weekend", sunday)[1] == datetime(2026, 10, 5, tzinfo=UTC)
    assert smart_coupon.period_window("week", friday)[1] == datetime(2026, 10, 9, tzinfo=UTC)
    assert smart_coupon.french_day(friday) == "vendredi 2 octobre"


def test_automatic_markets() -> None:
    from footprono.bookmaker.rules import automatic

    # Handicap asiatique : moins bien que pile ou face à la ligne du bookmaker.
    assert not automatic("AH")
    assert not automatic("CORNERS_AH")
    assert not automatic("CARDS_OU")
    assert automatic("OU")
    assert automatic("EH")


def test_withdrawn_markets() -> None:
    assert not offered("ODD_EVEN||odd")
    assert not offered("HT_BTTS||yes")
    assert not offered("HIGHEST_HALF||first")
    assert offered("BTTS||yes")
    assert offered("HT_OU|0.5|over")


async def test_smart_coupon_api(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
    db_factory: Factory,
) -> None:
    m1, m2 = world["m1"], world["m2"]
    await _predict(db_factory, [m1, m2])
    await _evening(db_factory, [m1, m2])
    headers = await _login(client)  # essai Premium à l'inscription

    r = await client.get(
        "/api/v1/smart-coupon",
        params={"profile": "equilibre", "period": "tomorrow", "size": 2},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    coupon = body["coupon"]
    # Victoire à domicile (60 %, cote 1,85) dans chaque match ; jamais deux sélections d'un match.
    picked = [(s["match_id"], s["market"], s["selection"]) for s in coupon["selections"]]
    assert sorted(picked) == sorted([(m1, "1X2", "home"), (m2, "1X2", "home")])
    assert coupon["total_odds"] == "3.42"
    assert coupon["probability"] == 0.36
    assert all(s["reasons"] for s in coupon["selections"])
    assert body["message"] is None

    # Aucune sélection « sûre » (75 % et plus) : dit clairement, rien d'inventé.
    sure = (
        await client.get(
            "/api/v1/smart-coupon", params={"profile": "sur", "period": "tomorrow"}, headers=headers
        )
    ).json()
    assert sure["coupon"] is None
    assert "Seulement 0 match" in sure["message"]

    # Rien aujourd'hui (matchs demain soir) : la date des prochains matchs est donnée.
    today = (
        await client.get(
            "/api/v1/smart-coupon", params={"profile": "equilibre", "period": "today"},
            headers=headers,
        )
    ).json()  # fmt: skip
    if NOW.date() < DAY:
        assert today["coupon"] is None
        assert "Prochains matchs à partir du" in today["message"]
    # « Prochaine journée » : trouve toujours les prochains matchs, même après une trêve.
    nxt = (
        await client.get(
            "/api/v1/smart-coupon", params={"profile": "equilibre", "period": "next", "size": 2},
            headers=headers,
        )
    ).json()  # fmt: skip
    assert len(nxt["coupon"]["selections"]) == 2

    bad = await client.get("/api/v1/smart-coupon", params={"size": 9}, headers=headers)
    assert bad.status_code == 400
    assert (await client.get("/api/v1/smart-coupon")).status_code == 401


async def test_daily_coupons_settled_and_public(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
    db_factory: Factory,
) -> None:
    m1, m2 = world["m1"], world["m2"]
    await _predict(db_factory, [m1, m2])
    await _evening(db_factory, [m1, m2])
    async with db_factory() as session:
        created = await smart_coupon.create_daily(session, MORNING)
        assert created["sur"] == "aucune sélection"
        assert created["equilibre"].startswith("2 sélection(s)")
        again = await smart_coupon.create_daily(session, MORNING)
        assert again["equilibre"] == "déjà créé"

    # m1 1-0 : « audacieux » (+2,5 buts) perdu sans attendre m2 ; « équilibré » en cours.
    assert await _result(db_factory, m1, 1, 0) == {"won": 0, "lost": 1, "partial": 0, "void": 0}
    # m2 2-1 : « équilibré » gagné.
    assert await _result(db_factory, m2, 2, 1) == {"won": 1, "lost": 0, "partial": 0, "void": 0}

    public = (await client.get("/api/v1/smart-coupons/history")).json()
    status = {c["profile"]: c["status"] for c in public["coupons"]}
    assert status == {"equilibre": "won", "audacieux": "lost"}
    lost = next(c for c in public["coupons"] if c["profile"] == "audacieux")
    assert {s["match_id"]: s["result"] for s in lost["selections"]} == {m1: "loss", m2: "pending"}
    assert public["stats"]["equilibre"] == {
        "label": "Équilibré", "settled": 1, "won": 1, "announced": 0.36, "observed": 1.0,
    }  # fmt: skip
    assert public["stats"]["sur"]["settled"] == 0


async def test_withdrawn_market_not_offered(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
    db_factory: Factory,
) -> None:
    async with db_factory() as session:
        session.add(
            quote(world["m1"], "1xBet", "Odd/Even", "Odd", "1.90", NOW - timedelta(hours=1))
        )
        await session.commit()
    offer = (await client.get(f"/api/v1/matches/{world['m1']}/offer")).json()
    assert {o["market"] for o in offer} >= {"1X2"}
    assert "ODD_EVEN" not in {o["market"] for o in offer}
