"""Coupon intelligent (Premium), choix du moteur par match, historique des coupons du jour."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Query

from footprono.accounts.plans import is_premium, require_premium
from footprono.api.deps import CurrentUserDep, OptionalUserDep, RedisDep, SessionDep
from footprono.bookmaker import smart_coupon
from footprono.core.errors import AppError

router = APIRouter(tags=["coupon intelligent"])

# Version gratuite : le choix « Sûr » de chaque match ; les trois profils avec Premium.
FREE_PICKS = frozenset({"sur"})


@router.get("/smart-coupon/competitions")
async def competitions_of_period(
    session: SessionDep,
    period: str = "next",
    day: date | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, int]:
    """Compétitions qui ont des matchs à venir dans la période (et combien)."""
    return await smart_coupon.period_competitions(
        session, period, day=day, date_from=date_from, date_to=date_to
    )


@router.get("/smart-coupon")
async def generate(
    user: CurrentUserDep,
    session: SessionDep,
    redis: RedisDep,
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
    exclude_competitions: Annotated[list[str] | None, Query()] = None,
    variant: Annotated[
        int, Query(ge=0, le=99, description="« Un autre coupon » : tirage suivant du joueur")
    ] = 0,
    engine: Annotated[
        int, Query(ge=1, le=2, description="2 : moteur 2, en mode comparaison seulement")
    ] = 1,
) -> Any:
    require_premium(user, "coupon intelligent")
    if engine == 2 and not user.compare_engines:
        raise AppError("moteur 2 : active « Comparer les deux moteurs » dans ton profil")
    out = await smart_coupon.generate(
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
        exclude_competitions=exclude_competitions,
        redis=redis,
        # Chaque joueur son tirage parmi les sélections presque à égalité, le même toute la
        # journée (proposition du 07/11/2026 : pas tout le monde perdant le même jour).
        player=user.id,
        variant=variant,
        engine=engine,
    )
    if user.compare_engines and out["coupon"] is not None and target_odds is None:
        # Comparaison des moteurs (K6) : chaque proposition de chaque moteur est enregistrée,
        # jouée ou non, puis réglée (bilan à mise fixe).
        from footprono.bookmaker import engine_compare

        await engine_compare.record_proposals(
            session, engine, "coupon", [out["coupon"]], user_id=user.id
        )
        await session.commit()
    return out


@router.get("/reliability/engines")
async def engines_reliability(user: CurrentUserDep, session: SessionDep) -> Any:
    """Moteur 1 contre moteur 2 (maquette K6) : log loss sur les mêmes matchs, bilan à mise
    fixe de chaque proposition, verdict seulement avec assez de données."""
    from footprono.bookmaker import engine_compare

    if not user.compare_engines:
        raise AppError("comparaison : active « Comparer les deux moteurs » dans ton profil")
    return await engine_compare.comparison(session)


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
async def history(
    session: SessionDep,
    user: OptionalUserDep,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
) -> Any:
    """Public : les coupons du jour sont enregistrés avant les matchs, rien n'est effacé
    (page suivante : ``offset``) ; ceux qui ne sont pas encore réglés n'ont leurs
    sélections qu'avec Premium."""
    return await smart_coupon.history(session, offset=offset, premium=is_premium(user))


@router.get("/smart-coupons/day")
async def day_coupons(
    session: SessionDep,
    user: OptionalUserDep,
    day: date | None = None,
    engine: Annotated[
        int, Query(ge=1, le=2, description="2 : moteur 2, en mode comparaison seulement")
    ] = 1,
) -> Any:
    """Les coupons du jour d'une date (aujourd'hui par défaut), leur état en direct et les
    codes de réservation : sélections et codes avec Premium tant qu'ils ne sont pas réglés,
    profil, cote, chance et bilan pour tous."""
    if engine == 2 and (user is None or not user.compare_engines):
        raise AppError("moteur 2 : active « Comparer les deux moteurs » dans ton profil")
    return await smart_coupon.day_coupons(session, day, premium=is_premium(user), engine=engine)
