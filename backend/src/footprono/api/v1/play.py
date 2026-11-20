"""Mon plan de jeu et mes alertes de cote (maquettes 29 et 30 du nouveau visage)."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field

from footprono.api.deps import CurrentUserDep, SessionDep
from footprono.bookmaker import odds_alerts, play_plan

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
