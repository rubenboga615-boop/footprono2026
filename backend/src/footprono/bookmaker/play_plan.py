"""Mon plan de jeu (maquette 30 du nouveau visage) : jeu responsable appliqué par le serveur.

- Budget de la semaine : somme des mises depuis lundi 0 h (heure du pays du joueur).
- Limite de perte : mises moins gains des paris réglés depuis lundi ; une fois atteinte, plus
  de nouveau pari jusqu'à lundi.
- Mise maximale par pari.
- Pause de 24 h, 7 jours ou 30 jours : plus de pari ; elle ne s'annule pas.
- Rappel après une heure dans l'application (affiché par l'application).

Une limite plus stricte s'applique tout de suite. Une limite relevée ou retirée n'entre en
vigueur que 24 h plus tard, pour éviter les décisions sous le coup d'une perte.
"""

from datetime import UTC, datetime, time, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.accounts.models import User
from footprono.bookmaker.live_alerts import UTC_OFFSETS
from footprono.bookmaker.models import Bet
from footprono.bookmaker.play_models import PlayPlan
from footprono.core.errors import AppError
from footprono.notifications.service import money

LIMITS = ("weekly_budget", "loss_limit", "max_stake")
DELAY = timedelta(hours=24)
PAUSES = (1, 7, 30)  # jours
MIN_LIMIT = 100  # la mise minimale
MAX_LIMIT = 100_000_000


class PlanLimitError(AppError):
    code = "play_plan"


def week_start(country: str, now: datetime) -> datetime:
    """Lundi 0 h de la semaine en cours, à l'heure du pays du joueur (en UTC)."""
    offset = timedelta(hours=UTC_OFFSETS.get(country.upper(), 0))
    local = now.astimezone(UTC) + offset
    monday = local.date() - timedelta(days=local.weekday())
    return datetime.combine(monday, time(), UTC) - offset


async def get_plan(session: AsyncSession, user_id: int, now: datetime) -> PlayPlan | None:
    """Le plan du joueur, avec les limites relevées appliquées si leurs 24 h sont passées."""
    plan = await session.get(PlayPlan, user_id)
    if plan is not None and plan.pending and plan.pending_at and plan.pending_at + DELAY <= now:
        for k, v in plan.pending.items():
            if k in LIMITS:
                setattr(plan, k, v)
        plan.pending = None
        plan.pending_at = None
        await session.flush()
    return plan


async def week(session: AsyncSession, user: User, now: datetime) -> dict[str, Any]:
    start = week_start(user.country, now)
    staked, settled_stake, settled_payout = (
        await session.execute(
            select(
                func.coalesce(func.sum(Bet.stake).filter(Bet.placed_at >= start), 0),
                func.coalesce(
                    func.sum(Bet.stake).filter(Bet.status == "settled", Bet.settled_at >= start), 0
                ),
                func.coalesce(
                    func.sum(Bet.payout).filter(Bet.status == "settled", Bet.settled_at >= start), 0
                ),
            ).where(Bet.user_id == user.id)
        )
    ).one()
    return {
        "start": start,
        "staked": int(staked),
        "lost": max(0, int(settled_stake) - int(settled_payout)),
    }


async def check_bet(session: AsyncSession, user: User, stake: int, now: datetime) -> None:
    """Refuse un pari contraire au plan de jeu (appelé par ``place_bet``)."""
    plan = await get_plan(session, user.id, now)
    if plan is None:
        return
    cur = user.currency
    if plan.pause_until is not None and plan.pause_until > now:
        raise PlanLimitError(
            "Pause en cours : pas de nouveau pari avant le "
            f"{_local(plan.pause_until, user.country)}."
        )
    if plan.max_stake is not None and stake > plan.max_stake:
        raise PlanLimitError(
            f"Ton plan de jeu limite la mise à {money(plan.max_stake, cur)} par pari."
        )
    if plan.weekly_budget is None and plan.loss_limit is None:
        return
    w = await week(session, user, now)
    if plan.loss_limit is not None and w["lost"] >= plan.loss_limit:
        raise PlanLimitError(
            f"Limite de perte de la semaine atteinte ({money(w['lost'], cur)} perdus) : "
            "plus de pari jusqu'à lundi."
        )
    if plan.weekly_budget is not None and w["staked"] + stake > plan.weekly_budget:
        left = max(0, plan.weekly_budget - w["staked"])
        raise PlanLimitError(
            f"Budget de la semaine : {money(w['staked'], cur)} misés sur "
            f"{money(plan.weekly_budget, cur)}. Il reste {money(left, cur)} jusqu'à lundi."
        )


def _local(at: datetime, country: str) -> str:
    local = at.astimezone(UTC) + timedelta(hours=UTC_OFFSETS.get(country.upper(), 0))
    return local.strftime("%d/%m à %H:%M")


def _stricter(old: int | None, new: int | None) -> bool | None:
    """True plus strict, False plus souple, None identique."""
    if old == new:
        return None
    if new is None:
        return False
    return old is None or new < old


async def update(
    session: AsyncSession, user: User, changes: dict[str, Any], now: datetime
) -> PlayPlan:
    plan = await get_plan(session, user.id, now)
    if plan is None:
        plan = PlayPlan(user_id=user.id, reminder=False)
        session.add(plan)
    pending = dict(plan.pending or {})
    for k in LIMITS:
        if k not in changes:
            continue
        new = changes[k]
        if new is not None and not MIN_LIMIT <= int(new) <= MAX_LIMIT:
            raise AppError(f"montant entre {MIN_LIMIT} et {MAX_LIMIT}")
        new = None if new is None else int(new)
        match _stricter(getattr(plan, k), new):
            case True:
                setattr(plan, k, new)
                pending.pop(k, None)
            case False:
                pending[k] = new
            case None:
                pending.pop(k, None)
    if "reminder" in changes:
        plan.reminder = bool(changes["reminder"])
    if pending != (plan.pending or {}):
        # Le délai de 24 h repart à chaque nouvel assouplissement.
        plan.pending_at = now if pending else None
        plan.pending = pending or None
    await session.flush()
    return plan


async def pause(session: AsyncSession, user: User, days: int, now: datetime) -> PlayPlan:
    if days not in PAUSES:
        raise AppError("pause de 1, 7 ou 30 jours")
    plan = await get_plan(session, user.id, now)
    if plan is None:
        plan = PlayPlan(user_id=user.id, reminder=False)
        session.add(plan)
    until = now + timedelta(days=days)
    if plan.pause_until is None or plan.pause_until < until:
        plan.pause_until = until
    await session.flush()
    return plan


async def summary(session: AsyncSession, user: User, now: datetime) -> dict[str, Any]:
    plan = await get_plan(session, user.id, now)
    w = await week(session, user, now)
    out: dict[str, Any] = {
        "weekly_budget": None,
        "loss_limit": None,
        "max_stake": None,
        "reminder": False,
        "pause_until": None,
        "pending": None,
        "pending_applies_at": None,
        "week": w,
    }
    if plan is not None:
        paused = plan.pause_until is not None and plan.pause_until > now
        out |= {
            "weekly_budget": plan.weekly_budget,
            "loss_limit": plan.loss_limit,
            "max_stake": plan.max_stake,
            "reminder": plan.reminder,
            "pause_until": plan.pause_until if paused else None,
            "pending": plan.pending,
            "pending_applies_at": plan.pending_at + DELAY if plan.pending_at else None,
        }
    return out
