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
from footprono.bookmaker.settlement import (
    Grade,
    bet_outcome,
    counts_grade,
    goals_grade,
    live_grade,
)
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
    assert report == {"settled": 2, "resettled": 0, "pending": 0, "notified": 0}
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


async def test_each_selection_graded_as_soon_as_its_match_ends(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
    db_factory: Factory,
) -> None:
    """Combiné sur plusieurs matchs : comme chez un bookmaker, chaque sélection est notée dès
    la fin de son match (avant : « en attente » jusqu'au dernier match), et chaque match
    montre son état en direct (minute et score)."""
    from footprono.bookmaker.settlement import settle_bets

    headers = await _login(client)
    combo = (
        await client.post(
            "/api/v1/bets",
            json={
                "stake": 2_000,
                "selections": [_sel(world["m1"], "1X2", "home"), _sel(world["m2"], "1X2", "home")],
            },
            headers=headers,
        )
    ).json()
    before = (await client.get(f"/api/v1/bets/{combo['id']}", headers=headers)).json()
    assert [s["state"] for s in before["selections"]] == ["upcoming", "upcoming"]
    assert before["selections"][0]["kickoff_at"] is not None

    await _finish(db_factory, world["m1"], (2, 0), "api_football")
    async with db_factory() as session:
        await session.execute(
            update(Match)
            .where(Match.id == world["m2"])
            .values(api_status="2H", live_minute=67, live_home_goals=1, live_away_goals=1)
        )
        await session.commit()
        report = await settle_bets(session)
    assert report["pending"] == 1  # m2 pas fini : le pari reste ouvert

    bet = (await client.get(f"/api/v1/bets/{combo['id']}", headers=headers)).json()
    assert bet["status"] == "open"
    first, second = bet["selections"]
    assert (first["result"], first["state"], first["score"]) == ("win", "settled", [2, 0])
    assert (second["result"], second["state"]) == ("pending", "live")
    assert (second["minute"], second["score"]) == (67, [1, 1])
    assert second["now"] == "loss"  # victoire à domicile, 1-1 : perdante pour l'instant


def test_live_grade_same_rules_as_settlement() -> None:
    """« Gagnante pour l'instant » : le score actuel réglé comme un score final."""
    m = Match(live_home_goals=2, live_away_goals=1)
    assert live_grade(m, "OU", "2.5", "over") == "win"
    assert live_grade(m, "OU", "3.5", "over") == "loss"
    assert live_grade(m, "AH", "-0.75", "home") == "half_win"
    assert live_grade(m, "AH", "-1", "home") == "push"
    assert live_grade(m, "HT_1X2", "", "home") is None  # mi-temps : pas en direct
    assert live_grade(m, "CORNERS_OU", "9.5", "over") is None
    assert live_grade(Match(), "OU", "2.5", "over") is None


def test_early_decisions_only_when_nothing_can_change_them() -> None:
    """Plan du 10/11/2026, étape 2 : réglé dès que plus aucun but (corner) ne change rien."""
    from footprono.bookmaker.settlement import _grade, early_counts, early_goals

    def result(sel: Any) -> str | None:
        return None if sel is None else _grade(sel, Decimal(2)).result

    # 2-1 en cours de match.
    assert result(early_goals("OU", "OU|2.5|over", (2, 1), None)) == "win"
    assert result(early_goals("OU", "OU|2.5|under", (2, 1), None)) == "loss"
    assert result(early_goals("OU", "OU|3.5|over", (2, 1), None)) is None  # peut encore
    assert result(early_goals("1X2", "1X2||home", (3, 0), None)) is None  # jamais avant la fin
    assert result(early_goals("BTTS", "BTTS||yes", (2, 1), None)) == "win"
    assert result(early_goals("BTTS", "BTTS||no", (2, 1), None)) == "loss"
    assert result(early_goals("TEAM_OU_HOME", "TEAM_OU_HOME|1.5|over", (2, 1), None)) == "win"
    assert result(early_goals("WIN_TO_NIL", "WIN_TO_NIL||home", (2, 1), None)) == "loss"
    # 1re mi-temps : rien tant que la pause n'est pas sifflée, tout dès la pause.
    assert result(early_goals("HT_OU", "HT_OU|2.5|under", (1, 0), None)) is None
    assert result(early_goals("HT_OU", "HT_OU|2.5|under", (1, 0), (1, 0))) == "win"
    assert result(early_goals("HT_1X2", "HT_1X2||draw", (2, 1), (1, 1))) == "win"
    assert result(early_goals("HT_BTTS", "HT_BTTS||yes", (1, 0), (1, 0))) == "loss"
    # Corners : 10e corner, « plus de 9,5 » gagné ; « plus de 10,5 » attend.
    assert result(early_counts("corners", "CORNERS_OU|9.5|over", (6, 4))) == "win"
    assert result(early_counts("corners", "CORNERS_OU|9.5|under", (6, 4))) == "loss"
    assert result(early_counts("corners", "CORNERS_OU|10.5|over", (6, 4))) is None


async def test_bet_settled_during_the_match_from_settled_snapshots(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
    db_factory: Factory,
) -> None:
    """« Plus de 2,5 buts » payé pendant le match, une fois le 3e but vu sur un relevé d'au
    moins 4 minutes ; un 3e but annulé (VAR) dans ce délai ne paie rien ; prolongation : on
    attend la fin ; la 1re mi-temps réglée à la pause (constat du fondateur, 09/11/2026)."""
    from footprono.bookmaker.models import BetSelection
    from footprono.bookmaker.settlement import grade_selection, settle_bets
    from footprono.football.models import LiveSnapshot

    headers = await _login(client)
    bet = (
        await client.post(
            "/api/v1/bets",
            json={"stake": 1_000, "selections": [_sel(world["m1"], "OU", "over", "2.5")]},
            headers=headers,
        )
    ).json()
    now = datetime.now(UTC)

    async def live(status: str, minute: int, score: tuple[int, int], ago: int) -> None:
        async with db_factory() as session:
            await session.execute(
                update(Match)
                .where(Match.id == world["m1"])
                .values(
                    api_status=status, live_minute=minute,
                    live_home_goals=score[0], live_away_goals=score[1],
                    home_goals_ht=1 if status != "1H" else None,
                    away_goals_ht=0 if status != "1H" else None,
                )
            )  # fmt: skip
            session.add(
                LiveSnapshot(
                    match_id=world["m1"], taken_at=now - timedelta(minutes=ago), status=status,
                    minute=minute, extra=0, home_goals=score[0], away_goals=score[1],
                    home_stats={"Corner Kicks": 4}, away_stats={"Corner Kicks": 3},
                )
            )  # fmt: skip
            await session.commit()

    # 3e but il y a 2 minutes seulement : pas encore réglé (la VAR peut l'annuler).
    await live("2H", 60, (2, 1), ago=2)
    async with db_factory() as session:
        await settle_bets(session, now=now)
        assert (await session.get(Bet, bet["id"])).status == "open"  # type: ignore[union-attr]

    # Même relevé, 5 minutes plus tard : payé sans attendre la fin du match.
    async with db_factory() as session:
        report = await settle_bets(session, now=now + timedelta(minutes=3))
        paid = await session.get(Bet, bet["id"])
    assert report["settled"] == 1
    assert paid is not None
    assert (paid.status, paid.outcome) == ("settled", "won")

    async with db_factory() as session:
        probe = await session.get(Match, world["m1"])
        assert probe is not None

        def sel(market: str, line: str, choice: str) -> BetSelection:
            return BetSelection(
                match_id=world["m1"], market=market, line=line, selection=choice,
                odds=Decimal("1.80"),
            )  # fmt: skip

        later = now + timedelta(minutes=3)
        # 1re mi-temps finie 1-0 : « moins de 1,5 but en 1re mi-temps » gagné.
        grade = await grade_selection(session, sel("HT_OU", "1.5", "under"), later)
        assert grade is not None
        assert grade.result == "win"
        # Corners : 7 vus, « plus de 6,5 » gagné, « plus de 8,5 » attend.
        grade = await grade_selection(session, sel("CORNERS_OU", "6.5", "over"), later)
        assert grade is not None
        assert grade.result == "win"
        assert await grade_selection(session, sel("CORNERS_OU", "8.5", "over"), later) is None
        # Prolongation : les buts ne comptent plus pour les paris, on attend la fin.
        await session.execute(update(Match).where(Match.id == world["m1"]).values(api_status="ET"))
        await session.commit()
        assert await grade_selection(session, sel("OU", "3.5", "under"), later) is None


def test_same_odds_rounding_everywhere() -> None:
    """Rapport du 09/11/2026 : même coupon affiché 1,84 puis 1,83."""
    from footprono.bookmaker.odds_math import combined_odds, shown_odds

    total = combined_odds([Decimal("1.20"), Decimal("1.15"), Decimal("1.33")])
    assert total == Decimal("1.835")
    assert shown_odds(total) == Decimal("1.84")
    assert shown_odds(combined_odds([Decimal("1.25"), Decimal("1.46")])) == Decimal("1.83")


async def test_console_warns_about_bet_matches_without_live_follow(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
    db_factory: Factory,
) -> None:
    """Rapport du 09/11/2026 : un coupon réglé 24 h en retard. Un match de pari sans numéro
    API-Football n'est pas suivi en direct : la console le signale."""
    from footprono.console.dashboard import _unfollowed_matches

    headers = await _login(client)
    await client.post(
        "/api/v1/bets",
        json={"stake": 1_000, "selections": [_sel(world["m1"], "1X2", "home")]},
        headers=headers,
    )
    async with db_factory() as session:
        await session.execute(
            update(Match).where(Match.id == world["m1"]).values(api_football_id=None)
        )
        await session.commit()
        names = await _unfollowed_matches(session)
    assert len(names) == 1
    assert " - " in names[0]
