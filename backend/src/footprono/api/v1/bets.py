"""Bookmaker virtuel : offre d'un match, paris, historique (argent fictif)."""

from typing import Annotated

from fastapi import APIRouter, Query, status
from sqlalchemy import select
from sqlalchemy.orm import aliased

from footprono.accounts.plans import market_allowed
from footprono.api.deps import CurrentUserDep, OptionalUserDep, SessionDep
from footprono.bookmaker import service
from footprono.bookmaker.models import Bet, BetSelection
from footprono.bookmaker.schemas import BetIn, BetOut, BetSelectionOut, OfferOut
from footprono.core.errors import NotFoundError
from footprono.football.models import Match, Team

router = APIRouter(tags=["bookmaker virtuel"])


@router.get("/matches/{match_id}/offer", response_model=list[OfferOut])
async def match_offer(match_id: int, session: SessionDep, user: OptionalUserDep) -> list[OfferOut]:
    """Sélections jouables (cote réelle récente) avec la probabilité du moteur.

    Pas de mention « value » : la probabilité du moteur est une information.
    Version gratuite (ou sans connexion) : marchés 1X2, OU et BTTS seulement.
    """
    offers = await service.match_offer(session, match_id)
    probs = await service.model_probabilities(session, match_id)
    out = []
    for k, o in sorted(offers.items()):
        if not market_allowed(user, o.market):
            continue
        p = probs.get(k)
        out.append(
            OfferOut(
                market=o.market,
                line=o.line or None,
                selection=o.selection,
                odds=o.odds,
                bookmaker=o.bookmaker,
                label=o.label,
                fetched_at=o.fetched_at,
                model_probability=p,
                model_fair_odds=round(1 / p, 3) if p else None,
            )
        )
    return out


async def _bet_out(session: SessionDep, bet: Bet) -> BetOut:
    selections = list(
        await session.scalars(
            select(BetSelection).where(BetSelection.bet_id == bet.id).order_by(BetSelection.id)
        )
    )
    home, away = aliased(Team), aliased(Team)
    rows = await session.execute(
        select(Match.id, home.name, away.name, Match.kickoff_at)
        .join(home, home.id == Match.home_team_id)
        .join(away, away.id == Match.away_team_id)
        .where(Match.id.in_([s.match_id for s in selections]))
    )
    info = {mid: (h, a, k) for mid, h, a, k in rows.tuples()}
    out = []
    for s in selections:
        item = BetSelectionOut.model_validate(s)
        if s.match_id in info:
            item.home_team, item.away_team, item.kickoff_at = info[s.match_id]
        out.append(item)
    return BetOut(
        id=bet.id,
        kind=bet.kind,
        stake=bet.stake,
        currency=bet.currency,
        total_odds=bet.total_odds,
        potential_payout=bet.potential_payout,
        status=bet.status,
        outcome=bet.outcome,
        payout=bet.payout,
        placed_at=bet.placed_at,
        settled_at=bet.settled_at,
        montante_step_id=bet.montante_step_id,
        selections=out,
    )


@router.post("/bets", response_model=BetOut, status_code=status.HTTP_201_CREATED)
async def place_bet(body: BetIn, user: CurrentUserDep, session: SessionDep) -> BetOut:
    bet = await service.place_bet(
        session,
        user,
        [
            service.SelectionIn(s.match_id, s.market.upper(), s.line, s.selection, s.odds)
            for s in body.selections
        ],
        body.stake,
    )
    await session.commit()
    await session.refresh(bet)
    return await _bet_out(session, bet)


@router.get("/bets", response_model=list[BetOut])
async def list_bets(
    user: CurrentUserDep,
    session: SessionDep,
    status_: Annotated[str | None, Query(alias="status", description="open, settled, void")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> list[BetOut]:
    stmt = select(Bet).where(Bet.user_id == user.id)
    if status_:
        stmt = stmt.where(Bet.status == status_)
    bets = (await session.scalars(stmt.order_by(Bet.id.desc()).limit(limit))).all()
    return [await _bet_out(session, b) for b in bets]


@router.get("/bets/{bet_id}", response_model=BetOut)
async def get_bet(bet_id: int, user: CurrentUserDep, session: SessionDep) -> BetOut:
    bet = await session.get(Bet, bet_id)
    if bet is None or bet.user_id != user.id:
        raise NotFoundError(f"pari {bet_id} introuvable")
    return await _bet_out(session, bet)
