"""Administration des comptes : Premium, rôles, activation, statistiques.

En attendant le paiement Mobile Money (phase 6), l'administrateur active
Premium à la main. Chaque changement est inscrit dans ``subscription_events``
(qui, quand, combien de jours, jusqu'à quelle date).
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.accounts.models import SubscriptionEvent, User
from footprono.accounts.service import normalize_phone
from footprono.bookmaker.models import Bet
from footprono.core.errors import AppError, NotFoundError

MAX_GRANT_DAYS = 366


async def get_user(session: AsyncSession, user_id: int) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError(f"utilisateur {user_id} introuvable")
    return user


async def search_users(
    session: AsyncSession, query: str | None = None, *, limit: int = 50, offset: int = 0
) -> list[User]:
    stmt = select(User)
    if query:
        digits = "".join(c for c in query if c.isdigit())
        conditions: list[ColumnElement[bool]] = [User.display_name.ilike(f"%{query.strip()}%")]
        if digits:
            conditions.append(User.phone.contains(digits))
        stmt = stmt.where(or_(*conditions))
    rows = await session.scalars(stmt.order_by(User.id.desc()).limit(limit).offset(offset))
    return list(rows.all())


async def grant_premium(
    session: AsyncSession,
    admin: User | None,
    user: User,
    days: int,
    *,
    note: str | None = None,
    now: datetime | None = None,
) -> SubscriptionEvent:
    """Ajoute ``days`` jours de Premium, à la suite de la période en cours s'il y en a une."""
    if not 1 <= days <= MAX_GRANT_DAYS:
        raise AppError(f"durée de 1 à {MAX_GRANT_DAYS} jours")
    now = now or datetime.now(UTC)
    start = user.premium_until if user.is_premium(now) and user.premium_until else now
    user.premium_until = start + timedelta(days=days)
    event = SubscriptionEvent(
        user_id=user.id,
        kind="admin_grant",
        days=days,
        premium_until=user.premium_until,
        admin_id=admin.id if admin else None,
        note=note,
    )
    session.add(event)
    await session.flush()
    return event


async def revoke_premium(
    session: AsyncSession,
    admin: User | None,
    user: User,
    *,
    note: str | None = None,
    now: datetime | None = None,
) -> SubscriptionEvent:
    now = now or datetime.now(UTC)
    if not user.is_premium(now):
        raise AppError("cet utilisateur n'a pas Premium")
    user.premium_until = now
    event = SubscriptionEvent(
        user_id=user.id,
        kind="admin_revoke",
        days=0,
        premium_until=now,
        admin_id=admin.id if admin else None,
        note=note,
    )
    session.add(event)
    await session.flush()
    return event


async def set_active(session: AsyncSession, admin: User, user: User, active: bool) -> User:
    if user.id == admin.id and not active:
        raise AppError("un administrateur ne peut pas désactiver son propre compte")
    user.is_active = active
    await session.flush()
    return user


async def set_role(session: AsyncSession, phone: str, role: str) -> User:
    """Utilisé en ligne de commande (``footprono-admin``) : nommer le premier administrateur."""
    if role not in ("user", "admin"):
        raise AppError("rôle : user ou admin")
    user = await session.scalar(select(User).where(User.phone == normalize_phone(phone)))
    if user is None:
        raise NotFoundError(f"aucun compte avec le numéro {phone}")
    user.role = role
    await session.flush()
    return user


async def subscription_history(session: AsyncSession, user_id: int) -> list[SubscriptionEvent]:
    rows = await session.scalars(
        select(SubscriptionEvent)
        .where(SubscriptionEvent.user_id == user_id)
        .order_by(SubscriptionEvent.id.desc())
    )
    return list(rows.all())


async def stats(session: AsyncSession, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    week = now - timedelta(days=7)
    users = await session.scalar(select(func.count(User.id))) or 0
    active = await session.scalar(select(func.count(User.id)).where(User.is_active)) or 0
    premium = await session.scalar(select(func.count(User.id)).where(User.premium_until > now)) or 0
    # Premium en cours dont la dernière période vient de l'essai d'inscription.
    last_event = (
        select(SubscriptionEvent.user_id, func.max(SubscriptionEvent.id).label("id"))
        .group_by(SubscriptionEvent.user_id)
        .subquery()
    )
    trial = (
        await session.scalar(
            select(func.count())
            .select_from(SubscriptionEvent)
            .join(last_event, last_event.c.id == SubscriptionEvent.id)
            .join(User, User.id == SubscriptionEvent.user_id)
            .where(SubscriptionEvent.kind == "trial", User.premium_until > now)
        )
        or 0
    )
    new_users = (
        await session.scalar(select(func.count(User.id)).where(User.created_at >= week)) or 0
    )
    bets_week = await session.scalar(select(func.count(Bet.id)).where(Bet.placed_at >= week)) or 0
    return {
        "users": users,
        "active_users": active,
        "premium": premium,
        "premium_trial": trial,
        "premium_paid_or_granted": premium - trial,
        "new_users_7d": new_users,
        "bets_7d": bets_week,
    }
