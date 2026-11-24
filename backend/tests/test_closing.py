"""Cote de clôture et mesure en silence (plan qualité du 24/11/2026, étape 2)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono.bookmaker import closing, service
from footprono.bookmaker.models import BetSelection
from footprono.bookmaker.play_models import SilentPick
from footprono.bookmaker.smart_models import SmartCoupon
from footprono.football.models import Match, MatchStatus
from footprono.ingestion import live

from .test_bets import NOW, _login, _sel, quote, world  # noqa: F401 (fixture partagée)
from .test_montante import _predict

Factory = async_sessionmaker[AsyncSession]


async def _kickoff(factory: Factory, match_id: int, at: datetime) -> None:
    async with factory() as session:
        await session.execute(update(Match).where(Match.id == match_id).values(kickoff_at=at))
        await session.commit()


async def _finish(factory: Factory, match_id: int, home: int, away: int) -> None:
    async with factory() as session:
        await session.execute(
            update(Match)
            .where(Match.id == match_id)
            .values(status=MatchStatus.FINISHED, home_goals=home, away_goals=away, api_status="FT")
        )
        await session.commit()


async def test_closing_price_is_last_quote_before_kickoff(
    world: dict[str, Any],  # noqa: F811
    db_factory: Factory,
) -> None:
    kickoff = NOW + timedelta(days=1)
    before, after = kickoff - timedelta(minutes=15), kickoff + timedelta(minutes=30)
    async with db_factory() as session:
        session.add_all(
            [
                quote(world["m1"], "1xBet", "Match Winner", "Home", "1.80", before),
                quote(world["m1"], "1xBet", "Match Winner", "Home", "1.60", after),
            ]
        )
        await session.commit()
        prices = await closing.closing_prices(session, world["m1"], "1xBet", kickoff)
    assert prices["1X2||home"] == Decimal("1.80")  # pas la cote d'après le coup d'envoi
    assert prices["1X2||draw"] == Decimal("3.60")


async def test_occasions_recorded_silently_then_closing_and_result(
    world: dict[str, Any],  # noqa: F811
    client: Any,
    db_factory: Factory,
) -> None:
    await _predict(db_factory, [world["m1"], world["m2"]])
    service.clear_window_cache()
    async with db_factory() as session:
        # Moteur 60 % contre 1 / 1,85 = 54 % sur la victoire à domicile : une par match.
        assert await closing.record_occasions(session, NOW) == 2
        assert await closing.record_occasions(session, NOW) == 0  # une seule fois
        picks = (await session.scalars(select(SilentPick))).all()
    assert {(p.market, p.selection, p.odds) for p in picks} == {("1X2", "home", Decimal("1.85"))}

    # Un joueur parie le même match ; le match commence, la cote a baissé avant.
    headers = await _login(client)
    r = await client.post(
        "/api/v1/bets", json={"stake": 1000, "selections": [_sel(world["m1"], "1X2", "home")]},
        headers=headers,
    )  # fmt: skip
    assert r.status_code == 201, r.text
    kickoff = NOW + timedelta(minutes=10)
    await _kickoff(db_factory, world["m1"], kickoff)
    async with db_factory() as session:
        session.add(quote(world["m1"], "1xBet", "Match Winner", "Home", "1.70", NOW))
        session.add(
            SmartCoupon(
                day=NOW.date(), profile="sur", engine=1, size=1, total_odds=Decimal("1.85"),
                probability=0.6, status="pending",
                selections=[{
                    "match_id": world["m1"], "market": "1X2", "line": "", "selection": "home",
                    "odds": "1.85", "bookmaker": "1xBet", "model_probability": 0.6,
                    "result": "pending",
                }],
            )
        )  # fmt: skip
        await session.commit()
    await _finish(db_factory, world["m1"], 2, 0)
    async with db_factory() as session:
        filled = await closing.fill(session, NOW + timedelta(hours=3))
        assert (filled["bets"], filled["occasions"], filled["daily_coupons"]) == (1, 1, 1)
        sel = await session.scalar(select(BetSelection))
        assert sel is not None
        assert sel.closing_odds == Decimal("1.70")
        pick = await session.scalar(select(SilentPick).where(SilentPick.match_id == world["m1"]))
        assert pick is not None
        assert (pick.closing_odds, pick.result) == (Decimal("1.70"), "win")
        coupon = await session.scalar(select(SmartCoupon))
        assert coupon is not None
        assert coupon.selections[0]["closing_odds"] == "1.700"
        # Cherchée une seule fois.
        again = await closing.fill(session, NOW + timedelta(hours=4))
        assert again["bets"] == again["occasions"] == again["daily_coupons"] == 0
        report = await closing.report(session, NOW + timedelta(hours=4))
    occ = report["occasions"]["total"]
    # Une occasion réglée, gagnée à 1,85 : +850 F ; prise à 1,85, clôture 1,70 : battue.
    assert (occ["settled"], occ["won"], occ["profit"], occ["beat_closing"]) == (1, 1, 850, 1.0)
    assert "+5 à +10 pts" in report["occasions"]["by_band"]  # 60 % contre 54 %
    assert report["daily_coupon_selections"]["total"]["beat_closing"] == 1.0
    assert report["player_bets"]["total"]["with_closing"] == 1


async def test_closing_targets_only_proposed_matches_starting_soon(
    world: dict[str, Any],  # noqa: F811
    db_factory: Factory,
) -> None:
    now = datetime.now(UTC)
    async with db_factory() as session:
        for mid, fixture in ((world["m1"], 9001), (world["m2"], 9002)):
            await session.execute(
                update(Match)
                .where(Match.id == mid)
                .values(kickoff_at=now + timedelta(minutes=12), api_football_id=fixture)
            )
        session.add(
            SilentPick(
                source="occasion", day=now.date(), match_id=world["m1"], competition="EPL",
                market="1X2", line="", selection="home", bookmaker="1xBet",
                odds=Decimal("1.85"), engine=0.6,
            )
        )  # fmt: skip
        await session.commit()
        # Seul le match proposé (m1) est relu ; m2 commence aussi, mais rien n'y est proposé.
        assert await live.closing_targets(session, now) == [(world["m1"], 9001)]
        assert await live.closing_targets(session, now + timedelta(hours=1)) == []


def test_gap_bands() -> None:
    assert closing.band_of(4) == "+3 à +5 pts"
    assert closing.band_of(12.5) == "+10 à +15 pts"
    assert closing.band_of(29) == "+15 pts et plus"


def test_daily_coupons_closing_record() -> None:
    from footprono.bookmaker.smart_coupon import closing_record

    def coupon(*pairs: tuple[str, str | None]) -> SmartCoupon:
        return SmartCoupon(selections=[{"odds": o, "closing_odds": c} for o, c in pairs])

    record = closing_record([coupon(("1.85", "1.700"), ("1.40", "1.450")), coupon(("2.10", None))])
    assert record == {"selections": 2, "beat": 1, "share": 0.5}
    assert closing_record([])["share"] is None
