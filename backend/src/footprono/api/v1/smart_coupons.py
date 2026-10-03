"""Coupon intelligent (Premium), choix du moteur par match, historique des coupons du jour."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Query

from footprono.accounts.plans import is_premium, require_premium
from footprono.api.deps import CurrentUserDep, OptionalUserDep, SessionDep
from footprono.bookmaker import smart_coupon

router = APIRouter(tags=["coupon intelligent"])

# Version gratuite : le choix « Sûr » de chaque match ; les trois profils avec Premium.
FREE_PICKS = frozenset({"sur"})


@router.get("/smart-coupon")
async def generate(
    user: CurrentUserDep,
    session: SessionDep,
    profile: str = "equilibre",
    period: str = "3days",
    size: int = 3,
    competitions: Annotated[list[str] | None, Query()] = None,
    target_odds: Decimal | None = None,
    day: date | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    after_hour: int | None = None,
    exclude_matches: Annotated[list[int] | None, Query()] = None,
    exclude_teams: Annotated[list[int] | None, Query()] = None,
) -> Any:
    require_premium(user, "coupon intelligent")
    return await smart_coupon.generate(
        session,
        profile,
        period,
        size,
        competitions=competitions,
        target_odds=target_odds,
        day=day,
        date_from=date_from,
        date_to=date_to,
        after_hour=after_hour,
        exclude_matches=exclude_matches,
        exclude_teams=exclude_teams,
    )


@router.get("/matches/{match_id}/picks")
async def match_picks(match_id: int, session: SessionDep, user: OptionalUserDep) -> Any:
    """« Les choix du moteur » : la sélection de chaque profil pour ce match.

    La plus probable de la tranche du profil parmi les marchés retenus qui ont une
    vraie cote (la même que le Coupon intelligent) ; jamais présentée comme une
    bonne affaire.
    """
    premium = is_premium(user)
    angles = await smart_coupon.match_angles(session, match_id)
    picks: dict[str, Any] = {}
    for key, prof in smart_coupon.PROFILES.items():
        pick = angles.get(key)
        locked = not premium and key not in FREE_PICKS
        picks[key] = {
            "label": prof.label,
            "range": [prof.low, prof.high],
            "locked": locked,
            "selection": None if locked or pick is None else smart_coupon.selection_summary(pick),
        }
    return {"match_id": match_id, "picks": picks}


@router.get("/smart-coupons/history")
async def history(session: SessionDep) -> Any:
    """Public : les coupons du jour sont enregistrés avant les matchs, rien n'est effacé."""
    return await smart_coupon.history(session)
