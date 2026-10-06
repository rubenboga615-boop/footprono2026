"""Rappel avant la fin de Premium : 3 jours avant, la veille, une seule fois chacun."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono.accounts import admin
from footprono.accounts import service as accounts
from footprono.accounts.models import SubscriptionEvent, User
from footprono.accounts.reminders import KIND, send_premium_reminders
from footprono.notifications.models import Notification

from .conftest import make_settings

Factory = async_sessionmaker[AsyncSession]


async def _user(session: AsyncSession, phone: str, name: str) -> User:
    return await accounts.register(
        session, make_settings(), phone=phone, password="motdepasse-1",
        display_name=name, country="CI", adult=True,
    )  # fmt: skip


async def test_reminders_three_days_before_then_the_day_before(db_factory: Factory) -> None:
    now = datetime(2026, 10, 5, 10, 5, tzinfo=UTC)
    async with db_factory() as session:
        trial = await _user(session, "+2250700000101", "Essai")
        # Essai d'un compte créé avant leur suppression : le rappel le nomme encore.
        session.add(SubscriptionEvent(user_id=trial.id, kind="trial", days=7, premium_until=now))
        paid = await _user(session, "+2250700000102", "Payant")
        later = await _user(session, "+2250700000103", "Plus tard")
        await admin.grant_premium(session, None, paid, 30, now=now)  # activé par l'admin
        await session.flush()
        ends = {
            trial.id: now + timedelta(days=2, hours=20),  # dans 3 jours
            paid.id: now + timedelta(hours=9),  # demain
            later.id: now + timedelta(days=10),
        }
        for uid, end in ends.items():
            await session.execute(update(User).where(User.id == uid).values(premium_until=end))
        await session.commit()
        ids = (trial.id, paid.id)

    async with db_factory() as session:
        assert await send_premium_reminders(session, now) == 2
    async with db_factory() as session:
        assert await send_premium_reminders(session, now + timedelta(hours=1)) == 0  # déjà envoyés
        notes = {
            n.user_id: n
            for n in await session.scalars(select(Notification).where(Notification.kind == KIND))
        }
    assert set(notes) == set(ids)
    assert notes[ids[0]].title == "Ton essai Premium se termine dans 3 jours"
    assert notes[ids[1]].title == "Ton Premium se termine demain"
    assert "Passer Premium" in notes[ids[1]].body

    # Deux jours plus tard, l'essai arrive à la veille : second rappel.
    async with db_factory() as session:
        assert await send_premium_reminders(session, now + timedelta(days=2)) == 1
