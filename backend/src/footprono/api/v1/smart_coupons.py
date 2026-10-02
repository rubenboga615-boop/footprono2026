"""Coupon intelligent (Premium) et historique public des coupons du jour."""

from typing import Annotated, Any

from fastapi import APIRouter, Query

from footprono.accounts.plans import require_premium
from footprono.api.deps import CurrentUserDep, SessionDep
from footprono.bookmaker import smart_coupon

router = APIRouter(tags=["coupon intelligent"])


@router.get("/smart-coupon")
async def generate(
    user: CurrentUserDep,
    session: SessionDep,
    profile: str = "equilibre",
    period: str = "3days",
    size: int = 3,
    competitions: Annotated[list[str] | None, Query()] = None,
) -> Any:
    require_premium(user, "coupon intelligent")
    return await smart_coupon.generate(session, profile, period, size, competitions=competitions)


@router.get("/smart-coupons/history")
async def history(session: SessionDep) -> Any:
    """Public : les coupons du jour sont enregistrés avant les matchs, rien n'est effacé."""
    return await smart_coupon.history(session)
