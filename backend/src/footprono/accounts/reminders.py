"""Rappel avant la fin de Premium : 3 jours avant, puis la veille (une fois chacun).

Envoyé aussi à la fin des anciens essais d'inscription (supprimés). La notification arrive
dans l'application et sur le téléphone (Firebase), comme les autres.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.accounts.models import SubscriptionEvent, User
from footprono.notifications import service as notifications
from footprono.notifications.models import Notification

KIND = "premium_ending"
# (jours avant la fin, libellé) : la tâche passe une fois par jour, chaque fenêtre dure 24 h.
STEPS = ((3, "dans 3 jours"), (1, "demain"))


async def _is_trial(session: AsyncSession, user_id: int) -> bool:
    last = await session.scalar(
        select(SubscriptionEvent.kind)
        .where(SubscriptionEvent.user_id == user_id)
        .order_by(SubscriptionEvent.id.desc())
        .limit(1)
    )
    return last == "trial"


async def send_premium_reminders(session: AsyncSession, now: datetime | None = None) -> int:
    """Crée les rappels du jour (déjà envoyés : ignorés) ; renvoie leur nombre."""
    now = now or datetime.now(UTC)
    sent = 0
    for days, label in STEPS:
        users = (
            await session.scalars(
                select(User).where(
                    User.is_active,
                    User.premium_until > now + timedelta(days=days - 1),
                    User.premium_until <= now + timedelta(days=days),
                )
            )
        ).all()
        for user in users:
            assert user.premium_until is not None
            key = f"{days}j-{user.premium_until:%Y-%m-%d}"
            already = await session.scalar(
                select(Notification.id).where(
                    Notification.user_id == user.id,
                    Notification.kind == KIND,
                    Notification.data["key"].astext == key,
                )
            )
            if already is not None:
                continue
            what = "Ton essai Premium" if await _is_trial(session, user.id) else "Ton Premium"
            notifications.add(
                session, user.id, KIND, f"{what} se termine {label}",
                f"Fin le {user.premium_until:%d/%m à %H:%M} (GMT). Garde tous les marchés, "
                "l'analyse et le Coupon intelligent : Profil → Prolonger.",
                {"key": key, "screen": "premium"},
            )  # fmt: skip
            sent += 1
    await session.commit()
    return sent
