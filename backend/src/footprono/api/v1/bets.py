"""Bookmaker virtuel : offre d'un match, paris, historique (argent fictif)."""

from typing import Annotated, Any

from fastapi import APIRouter, Query, status
from sqlalchemy import select
from sqlalchemy.orm import aliased

from footprono.accounts.plans import PremiumRequiredError, market_allowed
from footprono.api.deps import CurrentUserDep, OptionalUserDep, SessionDep
from footprono.bookmaker import service
from footprono.bookmaker.models import Bet, BetSelection
from footprono.bookmaker.record import player_record
from footprono.bookmaker.schemas import (
    BetIn,
    BetOut,
    BetSelectionOut,
    OddsHistoryOut,
    OddsPointOut,
    OfferOut,
)
from footprono.bookmaker.service import key
from footprono.core.errors import NotFoundError
from footprono.football.models import Match, Team

router = APIRouter(tags=["bookmaker virtuel"])


@router.get("/matches/{match_id}/offer", response_model=list[OfferOut])
async def match_offer(match_id: int, session: SessionDep, user: OptionalUserDep) -> list[OfferOut]:
    """Sélections jouables (cote réelle récente) avec la probabilité du moteur.

    Pas de mention « value » : la probabilité du moteur est une information.
    Version gratuite (ou sans connexion) : marchés 1X2, OU et BTTS seulement.
    """
    return await _offers_out(session, match_id, user)


# Colonnes du tableau des matchs (version ordinateur).
MAIN_KEYS = ("1X2||home", "1X2||draw", "1X2||away", "OU|2.5|over", "BTTS||yes")
MAX_MAIN_MATCHES = 80


@router.get("/offers/main", response_model=dict[int, list[OfferOut]])
async def main_offers(
    session: SessionDep,
    user: OptionalUserDep,
    match_ids: Annotated[list[int], Query(max_length=MAX_MAIN_MATCHES)],
) -> dict[int, list[OfferOut]]:
    """Cotes réelles des colonnes du tableau des matchs (1, N, 2, +2,5 buts, les deux
    marquent), plusieurs matchs à la fois. Un match sans cote récente est absent."""
    out = {}
    for match_id in dict.fromkeys(match_ids):
        offers = await _offers_out(session, match_id, user, MAIN_KEYS)
        if offers:
            out[match_id] = offers
    return out


async def _offers_out(
    session: SessionDep, match_id: int, user: Any, keys: tuple[str, ...] | None = None
) -> list[OfferOut]:
    offers = await service.match_offer(session, match_id)
    probs = await service.model_probabilities(session, match_id)
    allowed = {
        k: o
        for k, o in offers.items()
        if market_allowed(user, o.market) and (keys is None or k in keys)
    }
    history = await service.offer_history(session, [o.quote_id for o in allowed.values()])
    out = []
    for k, o in sorted(allowed.items()):
        first = history.get(o.quote_id, [None])[0]
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
                opening_odds=first.price if first else None,
                opened_at=first.fetched_at if first else None,
                source_updated_at=o.source_updated_at,
                checked_at=o.checked_at,
            )
        )
    return out


@router.get("/matches/{match_id}/odds-history", response_model=OddsHistoryOut)
async def odds_history(
    match_id: int,
    session: SessionDep,
    user: OptionalUserDep,
    market: str,
    selection: str,
    line: str = "",
) -> OddsHistoryOut:
    """Mouvement de la cote jouable d'une sélection : chaque changement, avec son heure.

    Une information, pas un conseil : une cote bouge avec l'argent des parieurs et les
    nouvelles (blessures, compositions).
    """
    if not market_allowed(user, market):
        raise PremiumRequiredError(f"marché {market} : réservé à Premium")
    offers = await service.match_offer(session, match_id)
    o = offers.get(key(market, line, selection))
    if o is None:
        raise NotFoundError("aucune cote jouable pour cette sélection")
    rows = (await service.offer_history(session, [o.quote_id]))[o.quote_id]
    return OddsHistoryOut(
        market=o.market,
        line=o.line or None,
        selection=o.selection,
        bookmaker=o.bookmaker,
        label=o.label,
        points=[OddsPointOut(at=r.fetched_at, odds=r.price) for r in rows],
        last_seen_at=rows[-1].last_seen_at,
    )


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


@router.get("/me/record")
async def my_record(user: CurrentUserDep, session: SessionDep) -> dict[str, Any]:
    """Mon bilan : rendement, réussite par marché et championnat, annoncé contre réalisé."""
    return await player_record(session, user.id)


@router.get("/bets/{bet_id}", response_model=BetOut)
async def get_bet(bet_id: int, user: CurrentUserDep, session: SessionDep) -> BetOut:
    bet = await session.get(Bet, bet_id)
    if bet is None or bet.user_id != user.id:
        raise NotFoundError(f"pari {bet_id} introuvable")
    return await _bet_out(session, bet)
