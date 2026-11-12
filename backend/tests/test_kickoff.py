"""Rappel de coup d'envoi : chaque match d'un pari, groupé par joueur, jamais pour un pari placé
juste avant le match."""

from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono.bookmaker.kickoff import KIND, send_kickoff_reminders
from footprono.bookmaker.models import Bet, BetSelection
from footprono.football.models import Match
from footprono.notifications.models import Notification

from .test_bets import NOW, world  # noqa: F401 (fixture partagée)

Factory = async_sessionmaker[AsyncSession]


async def _bet(session: AsyncSession, user_id: int, matches: list[int], placed: Any) -> int:
    bet = Bet(
        user_id=user_id, kind="combo" if len(matches) > 1 else "single", stake=1000,
        currency="XOF", total_odds=Decimal("3.4"), potential_payout=3400, placed_at=placed,
    )  # fmt: skip
    session.add(bet)
    await session.flush()
    for m in matches:
        session.add(
            BetSelection(
                bet_id=bet.id, match_id=m, market="1X2", selection="home",
                odds=Decimal("1.85"), bookmaker="1xBet",
            )
        )  # fmt: skip
    return bet.id


async def test_kickoff_reminder_for_each_match_grouped_by_player(
    world: dict[str, Any],  # noqa: F811
    db_factory: Factory,
) -> None:
    """Retour du testeur du 12/11/2026 : un rappel 30 min avant **chaque** match d'un pari en
    cours (avant : le premier seulement) ; matchs de la même fenêtre dans un seul message ;
    rien pour un pari placé moins de 30 min avant le match."""
    m1, m2 = world["m1"], world["m2"]
    async with db_factory() as session:
        # m1 dans 25 min, m2 dans 3 h.
        await session.execute(
            update(Match).where(Match.id == m1).values(kickoff_at=NOW + timedelta(minutes=25))
        )
        await session.execute(
            update(Match).where(Match.id == m2).values(kickoff_at=NOW + timedelta(hours=3))
        )
        user = world["user_id"]
        combo = await _bet(session, user, [m2, m1], NOW - timedelta(hours=2))
        single = await _bet(session, user, [m1], NOW - timedelta(hours=1))
        later = await _bet(session, user, [m2], NOW - timedelta(hours=1))
        late = await _bet(session, user, [m1], NOW - timedelta(minutes=2))  # placé juste avant
        await session.commit()

        assert await send_kickoff_reminders(session, NOW) == 1
        assert await send_kickoff_reminders(session, NOW + timedelta(minutes=5)) == 0
        notes = (await session.scalars(select(Notification).where(Notification.kind == KIND))).all()
    assert len(notes) == 1
    # Un match, deux coupons : un seul message, le match cité une fois.
    assert notes[0].title == "⏰ Ton match commence bientôt"
    assert notes[0].body.startswith("⏰ Dans 25 min : ")
    assert f"(tes coupons n° {min(combo, single)} et {max(combo, single)})" in notes[0].body
    assert sorted(notes[0].data["bets"]) == sorted([combo, single])
    assert late not in notes[0].data["bets"]
    assert notes[0].data["matches"] == [m1]

    # Trois heures plus tard : m2, pour le combiné (2e match) et le pari simple.
    async with db_factory() as session:
        assert await send_kickoff_reminders(session, NOW + timedelta(hours=2, minutes=40)) == 1
        last = await session.scalar(
            select(Notification).where(Notification.kind == KIND).order_by(Notification.id.desc())
        )
    assert last is not None
    assert last.title == "⏰ Ton match commence bientôt"
    assert last.body.startswith("⏰ Dans 20 min : ")
    assert sorted(last.data["bets"]) == sorted([combo, later])
    assert last.data["matches"] == [m2]


async def test_kickoff_reminder_names_every_match_of_the_window(
    world: dict[str, Any],  # noqa: F811
    db_factory: Factory,
) -> None:
    """Plusieurs matchs dans la même demi-heure : un message qui les cite tous, et un titre
    sans le délai du seul premier match."""
    m1, m2 = world["m1"], world["m2"]
    async with db_factory() as session:
        await session.execute(
            update(Match).where(Match.id == m1).values(kickoff_at=NOW + timedelta(minutes=20))
        )
        await session.execute(
            update(Match).where(Match.id == m2).values(kickoff_at=NOW + timedelta(minutes=28))
        )
        combo = await _bet(session, world["user_id"], [m1, m2], NOW - timedelta(hours=2))
        await session.commit()
        assert await send_kickoff_reminders(session, NOW) == 1
        note = await session.scalar(select(Notification).where(Notification.kind == KIND))
    assert note is not None
    assert note.title == "⏰ 2 de tes matchs commencent bientôt"
    lines = note.body.split("\n")
    assert lines[0].startswith("⏰ Dans 20 min : ")
    assert lines[1].startswith("⏰ Dans 28 min : ")
    assert f"(ton coupon n° {combo}, 0 sur 2 validée)" in lines[0]
    assert note.data["bet_id"] == combo
