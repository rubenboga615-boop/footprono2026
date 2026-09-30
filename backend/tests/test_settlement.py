"""Règlement des paris : mêmes calculs que les probabilités, du pari au solde."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono.accounts.models import Wallet, WalletEntry
from footprono.bookmaker.models import Bet
from footprono.bookmaker.settlement import Grade, bet_outcome, counts_grade, goals_grade
from footprono.football.models import Match, MatchStatus

from .test_bets import _login, _sel, world  # noqa: F401 (fixture partagée)

Factory = async_sessionmaker[AsyncSession]


def _match(ft: tuple[int, int], ht: tuple[int, int] | None, **stats: int) -> Match:
    return Match(
        id=1, season_id=1, home_team_id=10, away_team_id=20, match_date=date(2026, 10, 10),
        status=MatchStatus.FINISHED, home_goals=ft[0], away_goals=ft[1],
        home_goals_ht=ht[0] if ht else None, away_goals_ht=ht[1] if ht else None,
        result_source="football_data", **stats,
    )  # fmt: skip


@pytest.mark.parametrize(
    ("market", "key", "expected"),
    [
        ("1X2", "1X2||home", "win"),
        ("1X2", "1X2||draw", "loss"),
        ("OU", "OU|2.5|over", "win"),
        ("BTTS", "BTTS||yes", "win"),
        ("CS", "CS||2-1", "win"),
        ("AH", "AH|-0.75|home", "half_win"),  # -0,5 gagné, -1 remboursé
        ("AH", "AH|-1|home", "push"),
        ("AH", "AH|-0.25|away", "loss"),  # côté extérieur du handicap domicile -0,25
        ("AH", "AH|-1.25|home", "half_loss"),
        ("EH", "EH|-1|draw", "win"),  # 2-1 avec -1 : nul
        ("DNB", "DNB||away", "loss"),
        ("MARGIN", "MARGIN||home+1", "win"),
        ("1X2_OU", "1X2_OU|2.5|home/over", "win"),
        ("HTFT", "HTFT||draw/home", "win"),
        ("HT_1X2", "HT_1X2||draw", "win"),
        ("HIGHEST_HALF", "HIGHEST_HALF||first", "win"),  # 2 buts en 1re, 1 en 2e
    ],
)
def test_goals_markets_are_graded_like_they_are_priced(
    market: str, key: str, expected: str
) -> None:
    sel = goals_grade(_match((2, 1), (1, 1)), market, key)
    assert sel is not None
    grades = {
        "win": sel.win,
        "half_win": sel.half_win,
        "push": sel.push,
        "half_loss": sel.half_loss,
    }
    assert grades.get(expected, 1 - sum(grades.values())) == pytest.approx(1.0)


def test_half_time_market_waits_for_half_time_score() -> None:
    assert goals_grade(_match((2, 1), None), "HT_1X2", "HT_1X2||home") is None
    assert goals_grade(_match((2, 1), None), "1X2", "1X2||home") is not None


def test_counts_markets() -> None:
    match = _match(
        (0, 0), (0, 0), home_corners=6, away_corners=5, home_yellow_cards=3, away_yellow_cards=2,
        home_red_cards=1, away_red_cards=0,
    )  # fmt: skip
    over = counts_grade(match, {}, "CORNERS_OU", "CORNERS_OU|9.5|over")
    assert over is not None
    assert over.win == 1.0
    cards = counts_grade(match, {}, "CARDS_OU", "CARDS_OU|5.5|over")
    assert cards is not None
    assert cards.win == 1.0  # 6 cartons (jaunes + rouge)
    points = counts_grade(match, {}, "BOOKING_POINTS_OU", "BOOKING_POINTS_OU|65.5|over")
    assert points is not None
    assert points.win == 1.0  # 5 jaunes x 10 + 1 rouge x 25 = 75


def test_bet_outcome_combines_partial_results() -> None:
    grades = [
        Grade("win", Decimal("1.85")),
        Grade("half_win", Decimal("1.45")),
        Grade("push", Decimal(1)),
    ]
    assert bet_outcome(1000, grades) == ("partial", 2682)  # 1000 x 1,85 x 1,45, arrondi inférieur
    assert bet_outcome(1000, [Grade("push", Decimal(1))]) == ("push", 1000)
    assert bet_outcome(1000, [Grade("win", Decimal("2")), Grade("loss", Decimal(0))]) == ("lost", 0)


async def _finish(factory: Factory, match_id: int, ft: tuple[int, int], source: str) -> None:
    async with factory() as session:
        await session.execute(
            update(Match)
            .where(Match.id == match_id)
            .values(
                status=MatchStatus.FINISHED, home_goals=ft[0], away_goals=ft[1],
                home_goals_ht=0, away_goals_ht=0, result_source=source, api_status="FT",
            )
        )  # fmt: skip
        await session.commit()


async def test_bet_to_balance_end_to_end(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
    db_factory: Factory,
) -> None:
    from footprono.bookmaker.settlement import settle_bets

    headers = await _login(client)
    single = (
        await client.post(
            "/api/v1/bets",
            json={"stake": 10_000, "selections": [_sel(world["m1"], "1X2", "home")]},
            headers=headers,
        )
    ).json()
    combo = (
        await client.post(
            "/api/v1/bets",
            json={
                "stake": 2_000,
                "selections": [_sel(world["m1"], "1X2", "draw"), _sel(world["m2"], "1X2", "away")],
            },
            headers=headers,
        )
    ).json()

    # m1 se termine 2-0 (provisoire, API-Football) : le simple est gagné ; le
    # combiné est perdu tout de suite, sans attendre m2.
    await _finish(db_factory, world["m1"], (2, 0), "api_football")
    async with db_factory() as session:
        report = await settle_bets(session)
    assert report == {"settled": 2, "resettled": 0, "pending": 0}
    async with db_factory() as session:
        s = await session.get(Bet, single["id"])
        c = await session.get(Bet, combo["id"])
        wallet = await session.get(Wallet, world["user_id"])
    assert s is not None
    assert c is not None
    assert wallet is not None
    assert (s.outcome, s.payout) == ("won", 18_500)
    assert (c.outcome, c.payout) == ("lost", 0)
    assert wallet.balance == 100_000 - 10_000 - 2_000 + 18_500

    # Le lendemain, football-data corrige le score : 1-1. Le simple devient perdu,
    # le gain est repris avec une note ; relancer le règlement ne change plus rien.
    await _finish(db_factory, world["m1"], (1, 1), "football_data")
    async with db_factory() as session:
        again = await settle_bets(session)
        entries = (
            await session.scalars(select(WalletEntry).where(WalletEntry.kind == "correction"))
        ).all()
    assert again["resettled"] == 1
    assert [e.amount for e in entries] == [-18_500]
    assert "score corrigé" in (entries[0].note or "")
    async with db_factory() as session:
        assert (await settle_bets(session))["resettled"] == 0

    history = (await client.get(f"/api/v1/bets/{single['id']}", headers=headers)).json()
    assert (history["outcome"], history["payout"], history["selections"][0]["result"]) == (
        "lost", 0, "loss",
    )  # fmt: skip


async def test_postponed_match_is_refunded_after_48h(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
    db_factory: Factory,
) -> None:
    from footprono.bookmaker.settlement import settle_bets

    headers = await _login(client)
    bet = (
        await client.post(
            "/api/v1/bets",
            json={"stake": 3_000, "selections": [_sel(world["m2"], "1X2", "home")]},
            headers=headers,
        )
    ).json()
    async with db_factory() as session:
        await session.execute(
            update(Match)
            .where(Match.id == world["m2"])
            .values(api_status="PST", kickoff_at=datetime.now(UTC) - timedelta(hours=49))
        )
        await session.commit()
    async with db_factory() as session:
        await settle_bets(session)
        refunded = await session.get(Bet, bet["id"])
    assert refunded is not None
    assert (refunded.outcome, refunded.payout) == ("push", 3_000)
