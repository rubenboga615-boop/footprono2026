"""Mon plan de jeu, mes alertes de cote et mes équipes suivies (maquettes 26, 29 et 30)."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select

from footprono.api.deps import CurrentUserDep, SessionDep
from footprono.bookmaker import odds_alerts, play_plan
from footprono.bookmaker.play_models import FollowedTeam
from footprono.core.errors import AppError, NotFoundError
from footprono.football.models import Team

router = APIRouter(tags=["plan de jeu et alertes"])


class PlanIn(BaseModel):
    """Champs absents : inchangés ; ``null`` : limite retirée (après 24 h)."""

    model_config = {"extra": "forbid"}
    weekly_budget: int | None = Field(default=None, ge=play_plan.MIN_LIMIT, le=play_plan.MAX_LIMIT)
    loss_limit: int | None = Field(default=None, ge=play_plan.MIN_LIMIT, le=play_plan.MAX_LIMIT)
    max_stake: int | None = Field(default=None, ge=play_plan.MIN_LIMIT, le=play_plan.MAX_LIMIT)
    reminder: bool | None = None


class PauseIn(BaseModel):
    days: Literal[1, 7, 30]


@router.get("/me/play-plan")
async def get_plan(user: CurrentUserDep, session: SessionDep) -> Any:
    out = await play_plan.summary(session, user, datetime.now(UTC))
    await session.commit()
    return jsonable_encoder(out)


@router.put("/me/play-plan")
async def put_plan(body: PlanIn, user: CurrentUserDep, session: SessionDep) -> Any:
    now = datetime.now(UTC)
    changes = body.model_dump(exclude_unset=True)
    if changes.get("reminder", True) is None:
        changes.pop("reminder")
    await play_plan.update(session, user, changes, now)
    out = await play_plan.summary(session, user, now)
    await session.commit()
    return jsonable_encoder(out)


@router.post("/me/play-plan/pause")
async def post_pause(body: PauseIn, user: CurrentUserDep, session: SessionDep) -> Any:
    now = datetime.now(UTC)
    await play_plan.pause(session, user, body.days, now)
    out = await play_plan.summary(session, user, now)
    await session.commit()
    return jsonable_encoder(out)


class SelectionAlertIn(BaseModel):
    match_id: int = Field(ge=1, le=2_147_483_647)
    market: str = Field(max_length=40)
    line: str = Field(default="", max_length=10)
    selection: str = Field(max_length=40)
    target_odds: Decimal = Field(gt=1, le=1000, decimal_places=2)


class GapAlertIn(BaseModel):
    min_gap: float
    active: bool = True


class ActiveIn(BaseModel):
    active: bool


@router.get("/me/odds-alerts")
async def list_alerts(user: CurrentUserDep, session: SessionDep) -> Any:
    return jsonable_encoder(await odds_alerts.listing(session, user))


@router.post("/me/odds-alerts", status_code=status.HTTP_201_CREATED)
async def create_alert(body: SelectionAlertIn, user: CurrentUserDep, session: SessionDep) -> Any:
    alert = await odds_alerts.create_selection(
        session, user, body.match_id, body.market, body.line, body.selection, body.target_odds
    )
    await session.commit()
    return {"id": alert.id}


@router.put("/me/odds-alerts/gap")
async def put_gap(body: GapAlertIn, user: CurrentUserDep, session: SessionDep) -> Any:
    alert = await odds_alerts.set_gap(session, user, body.min_gap, body.active)
    await session.commit()
    return {"id": alert.id, "min_gap": alert.min_gap, "active": alert.active}


@router.patch("/me/odds-alerts/{alert_id}")
async def patch_alert(
    alert_id: int, body: ActiveIn, user: CurrentUserDep, session: SessionDep
) -> Any:
    alert = await odds_alerts.set_active(session, user, alert_id, body.active)
    await session.commit()
    return {"id": alert.id, "active": alert.active}


@router.delete("/me/odds-alerts/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert(alert_id: int, user: CurrentUserDep, session: SessionDep) -> None:
    await odds_alerts.remove(session, user, alert_id)
    await session.commit()


MAX_FOLLOWED = 50


@router.get("/me/followed-teams")
async def followed_teams(user: CurrentUserDep, session: SessionDep) -> list[int]:
    """Équipes que je suis (maquette 26) : filtre « Suivis » de la liste des matchs."""
    rows = await session.scalars(
        select(FollowedTeam.team_id).where(FollowedTeam.user_id == user.id)
    )
    return list(rows.all())


@router.put("/me/followed-teams/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def follow_team(team_id: int, user: CurrentUserDep, session: SessionDep) -> None:
    if not 1 <= team_id <= 2_147_483_647 or await session.get(Team, team_id) is None:
        raise NotFoundError("équipe introuvable")
    if await session.get(FollowedTeam, (user.id, team_id)) is not None:
        return
    n = await session.scalar(
        select(func.count()).select_from(FollowedTeam).where(FollowedTeam.user_id == user.id)
    )
    if (n or 0) >= MAX_FOLLOWED:
        raise AppError(f"{MAX_FOLLOWED} équipes suivies au plus")
    session.add(FollowedTeam(user_id=user.id, team_id=team_id))
    await session.commit()


@router.delete("/me/followed-teams/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unfollow_team(team_id: int, user: CurrentUserDep, session: SessionDep) -> None:
    await session.execute(
        delete(FollowedTeam).where(FollowedTeam.user_id == user.id, FollowedTeam.team_id == team_id)
    )
    await session.commit()
