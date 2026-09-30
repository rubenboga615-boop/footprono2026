"""Offre et prise de paris du bookmaker virtuel.

Cotes : **réelles**, dernier relevé 1xBet de la sélection, Bet365 en secours
(décision du 30/09/2026). Sans cote réelle récente, la sélection n'est pas
jouable : aucune cote n'est inventée.
"""

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.accounts import service as accounts
from footprono.accounts.models import User
from footprono.bookmaker.models import Bet, BetSelection
from footprono.core.errors import AppError, NotFoundError
from footprono.engine.markets import Selection
from footprono.football.models import BookmakerOdds, Match, MatchStatus
from footprono.ingestion.sources.api_football import UNPLAYED_STATUSES
from footprono.ingestion.sources.api_football_odds import map_bet
from footprono.predictions.models import MatchPrediction

PLAYABLE_BOOKMAKERS = ("1xBet", "Bet365")  # par ordre de préférence
ODDS_MAX_AGE = timedelta(hours=36)  # relevés deux fois par jour
MIN_STAKE = 100
MAX_SELECTIONS = 10


class OddsChangedError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "odds_changed"


@dataclass(frozen=True)
class Offer:
    market: str
    line: str
    selection: str
    odds: Decimal
    bookmaker: str
    quote_id: int
    fetched_at: datetime
    label: str  # libellé du bookmaker : « Match Winner — Home »


@dataclass(frozen=True)
class SelectionIn:
    match_id: int
    market: str
    line: str
    selection: str
    # Cote affichée à l'utilisateur : si la cote actuelle est plus basse, refus.
    odds: Decimal | None = None


def key(market: str, line: str, selection: str) -> str:
    return f"{market}|{line}|{selection}"


async def match_offer(
    session: AsyncSession, match_id: int, now: datetime | None = None
) -> dict[str, Offer]:
    """Cotes jouables d'un match, par clé du moteur (bookmaker préféré d'abord)."""
    now = now or datetime.now(UTC)
    last = (
        select(func.max(BookmakerOdds.id))
        .where(
            BookmakerOdds.match_id == match_id,
            BookmakerOdds.bookmaker.in_(PLAYABLE_BOOKMAKERS),
        )
        .group_by(BookmakerOdds.bookmaker, BookmakerOdds.bet, BookmakerOdds.value)
    )
    rows = (await session.scalars(select(BookmakerOdds).where(BookmakerOdds.id.in_(last)))).all()
    # Une cote ne compte que si le dernier relevé du bookmaker pour ce match la
    # contenait encore (sinon elle a été retirée) et si ce relevé est récent.
    latest_seen: dict[str, datetime] = {}
    for r in rows:
        latest_seen[r.bookmaker] = max(latest_seen.get(r.bookmaker, r.last_seen_at), r.last_seen_at)
    offers: dict[str, Offer] = {}
    rank = {b: i for i, b in enumerate(PLAYABLE_BOOKMAKERS)}
    for r in sorted(rows, key=lambda r: rank[r.bookmaker]):
        mapped = map_bet(r.bet, r.value)
        withdrawn = r.last_seen_at < latest_seen[r.bookmaker]
        if mapped is None or withdrawn or now - r.last_seen_at > ODDS_MAX_AGE:
            continue
        k = key(*mapped)
        if k not in offers:
            offers[k] = Offer(
                *mapped,
                odds=r.price,
                bookmaker=r.bookmaker,
                quote_id=r.id,
                fetched_at=r.fetched_at,
                label=f"{r.bet} — {r.value}",
            )
    return offers


async def model_probabilities(session: AsyncSession, match_id: int) -> dict[str, float]:
    """Probabilité équivalente du moteur (dernière prédiction), par clé de marché."""
    pred = await session.scalar(
        select(MatchPrediction)
        .where(MatchPrediction.match_id == match_id)
        .order_by(MatchPrediction.run_id.desc())
        .limit(1)
    )
    if pred is None:
        return {}
    return {k: Selection(*row).effective_probability for k, row in pred.markets.items()}


def _check_open(match: Match, now: datetime) -> None:
    if match.status is not MatchStatus.SCHEDULED or match.api_status in UNPLAYED_STATUSES:
        raise AppError(f"match {match.id} fermé aux paris (terminé, reporté ou annulé)")
    started = (
        match.kickoff_at <= now if match.kickoff_at is not None else match.match_date < now.date()
    )
    if started or (match.api_status or "NS") not in ("NS", "TBD"):
        raise AppError(f"match {match.id} déjà commencé : paris fermés")


async def place_bet(
    session: AsyncSession,
    user: User,
    selections: list[SelectionIn],
    stake: int,
    *,
    now: datetime | None = None,
    montante_step_id: int | None = None,
) -> Bet:
    now = now or datetime.now(UTC)
    if not 1 <= len(selections) <= MAX_SELECTIONS:
        raise AppError(f"un pari compte de 1 à {MAX_SELECTIONS} sélections")
    if stake < MIN_STAKE:
        raise AppError(f"mise minimale : {MIN_STAKE} {user.currency}")
    match_ids = [s.match_id for s in selections]
    if len(set(match_ids)) != len(match_ids):
        raise AppError(
            "un combiné ne peut pas réunir deux sélections du même match (elles sont liées) : "
            "utiliser un marché combiné du bookmaker (résultat + les deux marquent…)"
        )
    chosen: list[tuple[SelectionIn, Offer, float | None]] = []
    for s in selections:
        match = await session.get(Match, s.match_id)
        if match is None:
            raise NotFoundError(f"match {s.match_id} introuvable")
        _check_open(match, now)
        offer = (await match_offer(session, s.match_id, now)).get(
            key(s.market, s.line, s.selection)
        )
        if offer is None:
            raise AppError(
                f"aucune cote réelle récente pour {s.market} {s.line} {s.selection} "
                f"(match {s.match_id}) : sélection non jouable"
            )
        if s.odds is not None and offer.odds < s.odds:
            raise OddsChangedError(
                f"la cote a baissé : {s.odds} → {offer.odds} ({offer.bookmaker})",
                details={"match_id": s.match_id, "odds": str(offer.odds)},
            )
        probs = await model_probabilities(session, s.match_id)
        chosen.append((s, offer, probs.get(key(s.market, s.line, s.selection))))

    total = Decimal(1)
    for _, offer, _ in chosen:
        total *= offer.odds
    total = total.quantize(Decimal("0.001"))
    bet = Bet(
        user_id=user.id,
        kind="single" if len(chosen) == 1 else "combo",
        stake=stake,
        currency=user.currency,
        total_odds=total,
        potential_payout=math.floor(stake * total),
        status="open",
        settlements=0,
        montante_step_id=montante_step_id,
    )
    session.add(bet)
    await session.flush()
    for s, offer, prob in chosen:
        session.add(
            BetSelection(
                bet_id=bet.id,
                match_id=s.match_id,
                market=s.market,
                line=s.line,
                selection=s.selection,
                odds=offer.odds,
                bookmaker=offer.bookmaker,
                odds_quote_id=offer.quote_id,
                model_probability=prob,
                result="pending",
            )
        )
    await accounts.move(session, user.id, -stake, "stake", bet_id=bet.id, note=f"pari {bet.id}")
    return bet
