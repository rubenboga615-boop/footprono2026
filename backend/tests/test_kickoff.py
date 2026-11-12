"""Rappel de coup d'envoi : une fois par pari, groupé par joueur, jamais pour un pari placé
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


async def test_kickoff_reminder_once_per_bet_grouped_by_player(
    world: dict[str, Any],  # noqa: F811
    db_factory: Factory,
) -> None:
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
        combo = await _bet(session, user, [m2, m1], NOW - timedelta(hours=2))  # 1er match : m1
        single = await _bet(session, user, [m1], NOW - timedelta(hours=1))
        later = await _bet(session, user, [m2], NOW - timedelta(hours=1))  # pas encore
        await _bet(session, user, [m1], NOW - timedelta(minutes=2))  # placé juste avant
        await session.commit()

        assert await send_kickoff_reminders(session, NOW) == 1  # un seul message, groupé
        assert await send_kickoff_reminders(session, NOW + timedelta(minutes=5)) == 0
        notes = (await session.scalars(select(Notification).where(Notification.kind == KIND))).all()
    assert len(notes) == 1
    assert notes[0].title == "2 de tes paris commencent bientôt"
    assert notes[0].body.endswith("commence dans 25 min. Suivi en direct dans Mes paris.")
    assert " - " in notes[0].body  # le match, pas un numéro
    assert sorted(notes[0].data["bets"]) == sorted([combo, single])
    assert later not in notes[0].data["bets"]

    # Trois heures plus tard : le pari sur m2 seul.
    async with db_factory() as session:
        assert await send_kickoff_reminders(session, NOW + timedelta(hours=2, minutes=40)) == 1
        last = await session.scalar(
            select(Notification).where(Notification.kind == KIND).order_by(Notification.id.desc())
        )
    assert last is not None
    assert last.title == "Ton pari commence dans 20 min"
    assert last.data["bets"] == [later]


def test_kickoff_text_names_every_match() -> None:
    """12/11/2026 : « 2 de tes paris commencent bientôt » ne citait que le premier match."""
    from footprono.bookmaker.kickoff import _starts_text

    assert _starts_text({"Arménie - Chypre": 30}) == "Arménie - Chypre commence dans 30 min."
    assert _starts_text({"Arménie - Chypre": 29, "Türkiye - Belgium": 30}) == (
        "Arménie - Chypre dans 29 min, Türkiye - Belgium dans 30 min."
    )
    many = {f"M{i} - N{i}": 30 for i in range(5)}
    assert _starts_text(many).endswith("M2 - N2 dans 30 min et 2 autres matchs.")
