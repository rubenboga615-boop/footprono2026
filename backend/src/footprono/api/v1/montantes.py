"""Montante : plan, pari du palier, suggestions, encaissement (argent fictif)."""

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from footprono.api.deps import CurrentUserDep, SessionDep
from footprono.api.v1.bets import _bet_out
from footprono.bookmaker import montante, service, suggestions
from footprono.bookmaker.montante_models import Montante, MontanteStep
from footprono.bookmaker.schemas import BetOut, SelectionIn
from footprono.core.errors import NotFoundError

router = APIRouter(tags=["montante"])


class RangeIn(BaseModel):
    odds_min: Decimal
    odds_max: Decimal


class MontanteIn(BaseModel):
    start_stake: int = montante.DEFAULT_START_STAKE
    secure_pct: int = Field(default=0, ge=0, le=90)
    steps: list[RangeIn] = Field(min_length=montante.MIN_STEPS, max_length=montante.MAX_STEPS)


class StepBetIn(BaseModel):
    selections: list[SelectionIn] = Field(min_length=1, max_length=3)
    accept_out_of_range: bool = False


@router.post("/montantes", status_code=status.HTTP_201_CREATED)
async def create_montante(body: MontanteIn, user: CurrentUserDep, session: SessionDep) -> Any:
    created = await montante.create(
        session,
        user,
        [(r.odds_min, r.odds_max) for r in body.steps],
        body.start_stake,
        body.secure_pct,
    )
    await session.commit()
    return await montante.plan(session, created)


@router.get("/montantes")
async def list_montantes(user: CurrentUserDep, session: SessionDep) -> list[Any]:
    rows = await session.scalars(
        select(Montante).where(Montante.user_id == user.id).order_by(Montante.id.desc()).limit(50)
    )
    return [await montante.plan(session, m) for m in rows.all()]


async def _own(session: SessionDep, user: CurrentUserDep, montante_id: int) -> Montante:
    m = await session.get(Montante, montante_id)
    if m is None or m.user_id != user.id:
        raise NotFoundError(f"montante {montante_id} introuvable")
    return m


@router.get("/montantes/{montante_id}")
async def get_montante(montante_id: int, user: CurrentUserDep, session: SessionDep) -> Any:
    return await montante.plan(session, await _own(session, user, montante_id))


@router.get("/montantes/{montante_id}/suggestions")
async def step_suggestions(montante_id: int, user: CurrentUserDep, session: SessionDep) -> Any:
    m = await _own(session, user, montante_id)
    step = await session.scalar(
        select(MontanteStep).where(
            MontanteStep.montante_id == m.id, MontanteStep.number == m.current_step
        )
    )
    assert step is not None
    return {
        "step": step.number,
        "odds_min": step.odds_min,
        "odds_max": step.odds_max,
        "stake": m.next_stake,
        "suggestions": await suggestions.suggest(session, step.odds_min, step.odds_max),
    }


@router.post("/montantes/{montante_id}/bet", response_model=BetOut, status_code=201)
async def step_bet(
    montante_id: int, body: StepBetIn, user: CurrentUserDep, session: SessionDep
) -> BetOut:
    bet = await montante.place_step_bet(
        session,
        user,
        montante_id,
        [
            service.SelectionIn(s.match_id, s.market.upper(), s.line, s.selection, s.odds)
            for s in body.selections
        ],
        accept_out_of_range=body.accept_out_of_range,
    )
    await session.commit()
    await session.refresh(bet)
    return await _bet_out(session, bet)


@router.post("/montantes/{montante_id}/cash-out")
async def cash_out(montante_id: int, user: CurrentUserDep, session: SessionDep) -> Any:
    m = await montante.cash_out(session, user, montante_id)
    await session.commit()
    return await montante.plan(session, m)
