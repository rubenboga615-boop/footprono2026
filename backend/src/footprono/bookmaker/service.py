"""Offre et prise de paris du bookmaker virtuel.

Cotes : **réelles**, dernier relevé 1xBet de la sélection, Bet365 en secours
(décision du 30/09/2026). Sans cote réelle récente, la sélection n'est pas
jouable : aucune cote n'est inventée.
"""

import asyncio
import math
import time
import weakref
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.accounts import service as accounts
from footprono.accounts.models import User
from footprono.accounts.plans import require_market
from footprono.bookmaker.models import Bet, BetSelection
from footprono.bookmaker.odds_math import combined_odds
from footprono.core.errors import AppError, NotFoundError
from footprono.engine.markets import WITHDRAWN_MARKETS, Selection
from footprono.football.models import BookmakerOdds, Match, MatchStatus
from footprono.ingestion.sources.api_football import UNPLAYED_STATUSES
from footprono.ingestion.sources.api_football_odds import map_bet
from footprono.predictions.models import MatchPrediction

PLAYABLE_BOOKMAKERS = ("1xBet", "Bet365")  # par ordre de préférence
ODDS_MAX_AGE = timedelta(hours=36)  # relevés toutes les 3 heures ; marge si l'API tombe
# Cote que la source elle-même n'a pas mise à jour depuis plus de 2 jours (rapport du
# 10/11/2026 : cotes de la CAN vieilles d'un mois) : montrée avec un avertissement, jamais
# choisie automatiquement (Coupon intelligent, Coupons du jour, suggestions de montante).
SOURCE_MAX_AGE = timedelta(days=2)


def fresh(offer: "Offer", now: datetime) -> bool:
    """Vrai si la source a mis la cote à jour récemment (ou ne dit pas quand)."""
    return offer.source_updated_at is None or now - offer.source_updated_at <= SOURCE_MAX_AGE


MIN_STAKE = 100
MAX_SELECTIONS = 12


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
    # Mise à jour de la cote chez la source (API-Football) et dernier relevé où elle
    # était encore proposée : une cote peut être relevée souvent sans être mise à jour.
    source_updated_at: datetime | None = None
    checked_at: datetime | None = None


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
    return (await match_offers(session, [match_id], now)).get(match_id, {})


async def match_offers(
    session: AsyncSession, match_ids: Sequence[int], now: datetime | None = None
) -> dict[int, dict[str, Offer]]:
    """Cotes jouables de plusieurs matchs en une requête : {match: {clé: offre}}.

    Une requête par match faisait attendre le Coupon intelligent plus de 20 secondes
    (des centaines de matchs, une fois par profil) : l'application affichait alors
    « Connexion trop lente » alors que le réseau allait bien."""
    now = now or datetime.now(UTC)
    if not match_ids:
        return {}
    o = BookmakerOdds
    last = (
        select(func.max(o.id))
        .where(o.match_id.in_(list(match_ids)), o.bookmaker.in_(PLAYABLE_BOOKMAKERS))
        .group_by(o.match_id, o.bookmaker, o.bet, o.value)
    )
    # Dernier relevé de chaque bookmaker pour le match : une cote absente de ce relevé a
    # été retirée. Calculé par la base, qui ne renvoie que les cotes encore valables.
    latest = (
        select(
            o.id, o.match_id, o.bookmaker, o.bet, o.value, o.price, o.fetched_at,
            o.source_updated_at, o.last_seen_at,
            func.max(o.last_seen_at)
            .over(partition_by=(o.match_id, o.bookmaker))
            .label("bookmaker_seen"),
        )
        .where(o.id.in_(last))
        .subquery()
    )  # fmt: skip
    rows = (
        await session.execute(
            select(latest).where(
                latest.c.last_seen_at >= latest.c.bookmaker_seen,
                latest.c.last_seen_at >= now - ODDS_MAX_AGE,
            )
        )
    ).all()
    out: dict[int, dict[str, Offer]] = {}
    rank = {b: i for i, b in enumerate(PLAYABLE_BOOKMAKERS)}
    for r in sorted(rows, key=lambda r: (rank[r.bookmaker], r.id)):
        mapped = map_bet(r.bet, r.value)
        if mapped is None or mapped[0] in WITHDRAWN_MARKETS:
            continue
        offers = out.setdefault(r.match_id, {})
        k = key(*mapped)
        if k not in offers:
            offers[k] = Offer(
                *mapped,
                odds=r.price,
                bookmaker=r.bookmaker,
                quote_id=r.id,
                fetched_at=r.fetched_at,
                label=f"{r.bet} — {r.value}",
                source_updated_at=r.source_updated_at,
                checked_at=r.last_seen_at,
            )
    return out


async def model_probabilities(session: AsyncSession, match_id: int) -> dict[str, float]:
    """Probabilité équivalente du moteur (dernière prédiction), par clé de marché."""
    return (await models_probabilities(session, [match_id])).get(match_id, {})


async def models_probabilities(
    session: AsyncSession, match_ids: Sequence[int]
) -> dict[int, dict[str, float]]:
    """Dernière prédiction de plusieurs matchs en une requête : {match: {clé: proba}}."""
    if not match_ids:
        return {}
    # Les marchés seulement : chaque version complète (contexte, moyennes) est lourde.
    preds = await session.execute(
        select(MatchPrediction.match_id, MatchPrediction.markets)
        .where(MatchPrediction.match_id.in_(list(match_ids)))
        .order_by(MatchPrediction.match_id, MatchPrediction.run_id.desc())
        .distinct(MatchPrediction.match_id)
    )
    return {
        match_id: {k: Selection(*row).effective_probability for k, row in markets.items()}
        for match_id, markets in preds.tuples()
    }


# Cotes et pronostics d'une période, gardés quelques minutes pour le Coupon intelligent,
# les coupons du jour et les suggestions de montante. Avant : 16 à 19 secondes par demande
# en production (06/11/2026), recalculées à chaque joueur et à chaque profil. Les cotes sont
# relevées toutes les 3 heures : 10 minutes de retard au plus ne changent pas le coupon, et
# la cote est toujours relue au moment du pari (``place_bet`` ne passe pas par ce cache).
WINDOW_CACHE_TTL = 600.0  # secondes
_window_cache: dict[int, tuple[float, dict[str, Offer], dict[str, float]]] = {}
_window_locks: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = (
    weakref.WeakKeyDictionary()
)  # un verrou par boucle d'événements (les tests en créent plusieurs)


def clear_window_cache() -> None:
    _window_cache.clear()


async def cached_offers_and_probabilities(
    session: AsyncSession, match_ids: Sequence[int], now: datetime | None = None
) -> tuple[dict[int, dict[str, Offer]], dict[int, dict[str, float]]]:
    """``match_offers`` et ``models_probabilities``, avec un cache de quelques minutes par match.

    Seuls les matchs absents ou expirés sont relus, en deux requêtes. Un verrou évite que
    plusieurs joueurs arrivés en même temps relisent tous la même période."""
    lock = _window_locks.setdefault(asyncio.get_running_loop(), asyncio.Lock())
    async with lock:
        clock = time.monotonic()
        for mid in [m for m, (at, *_) in _window_cache.items() if clock - at > WINDOW_CACHE_TTL]:
            del _window_cache[mid]
        missing = [m for m in dict.fromkeys(match_ids) if m not in _window_cache]
        if missing:
            offers = await match_offers(session, missing, now)
            probs = await models_probabilities(session, missing)
            for m in missing:
                _window_cache[m] = (clock, offers.get(m, {}), probs.get(m, {}))
        found = [(m, _window_cache[m]) for m in match_ids]
    return (
        {m: offers for m, (_, offers, _) in found if offers},
        {m: probs for m, (_, _, probs) in found if probs},
    )


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
    for s in selections:
        require_market(user, s.market, now)
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

    total = combined_odds(offer.odds for _, offer, _ in chosen)
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


async def offer_history(
    session: AsyncSession, quote_ids: list[int]
) -> dict[int, list[BookmakerOdds]]:
    """Relevés successifs (du plus ancien au plus récent) de la sélection de chaque cote.

    Une ligne n'existe que si la cote a changé : l'historique est donc la suite des
    mouvements, chacun avec son heure de relevé.
    """
    if not quote_ids:
        return {}
    current = (
        await session.scalars(select(BookmakerOdds).where(BookmakerOdds.id.in_(quote_ids)))
    ).all()
    out: dict[int, list[BookmakerOdds]] = {}
    for q in current:
        out[q.id] = list(
            await session.scalars(
                select(BookmakerOdds)
                .where(
                    BookmakerOdds.match_id == q.match_id,
                    BookmakerOdds.bookmaker == q.bookmaker,
                    BookmakerOdds.bet == q.bet,
                    BookmakerOdds.value == q.value,
                )
                .order_by(BookmakerOdds.fetched_at, BookmakerOdds.id)
            )
        )
    return out
