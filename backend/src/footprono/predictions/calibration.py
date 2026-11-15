"""Probabilités servies à l'application : moteur calé sur la cote de référence (moteur 3.0).

Pour chaque match : la dernière prévision du moteur (λ, rho, parts de mi-temps, marchés) et
les dernières cotes du bookmaker de référence. Si le 1-N-2 de référence est complet, la loi
des scores est calée dessus (``engine.market_fit``) et **tous les marchés de buts** sont
recalculés à partir de cette loi ; corners, cartons et tirs restent ceux du moteur (seuls
marchés où il fait jeu égal avec la référence, docs/ETUDE_MOTEUR_V3_2026-11-15.md).

Jamais de donnée inventée : sans cote de référence récente, ou si le calage est refusé,
les probabilités du moteur sont servies telles quelles et ``calibrated`` vaut faux.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.engine.market_fit import fit_rates, reference_target
from footprono.engine.markets import Selection, derive_markets
from footprono.engine.scores import score_distribution
from footprono.football.models import BookmakerOdds
from footprono.ingestion.sources.api_football_odds import map_bet
from footprono.predictions.models import MatchPrediction

# Bookmaker dont les cotes servent de référence : marge la plus basse sur le vainqueur et
# les buts (4,5 % et 4,8 % contre 7,7 % et 5,6 % chez Bet365, relevés du 30/09 au
# 14/11/2026), et meilleure log loss des cotes d'avant-match de l'archive football-data.
REFERENCE_BOOKMAKER = "Pinnacle"
# Même fraîcheur que les cotes jouables (``bookmaker.service.ODDS_MAX_AGE``).
REFERENCE_MAX_AGE = timedelta(hours=36)


@dataclass(frozen=True)
class Calibrated:
    probabilities: dict[str, float]  # clé du moteur → probabilité équivalente
    calibrated: bool  # faux : probabilités du moteur seul
    lambda_home: float
    lambda_away: float
    fit_error: float | None = None


def calibrate(
    lam_home: float,
    lam_away: float,
    rho: float,
    share_home: float,
    share_away: float,
    markets: Mapping[str, Sequence[float]],
    reference: Mapping[str, float],
) -> Calibrated:
    """Probabilités d'un match, calées sur ``reference`` (clé du moteur → cote) si possible.

    Seules les clés déjà présentes dans ``markets`` sont servies : les règles du moteur sur
    les marchés proposés par championnat (``tiers.market_allowed``) restent appliquées.
    """
    engine = {k: Selection(*row).effective_probability for k, row in markets.items()}
    target = reference_target(reference) if reference else None
    fit = None if target is None else fit_rates(target, rho, (lam_home, lam_away))
    if fit is None:
        return Calibrated(engine, False, lam_home, lam_away)
    dist = score_distribution(fit.lam_home, fit.lam_away, rho, share_home, share_away)
    goals = derive_markets(dist)
    out = {k: (goals[k].effective_probability if k in goals else p) for k, p in engine.items()}
    return Calibrated(out, True, fit.lam_home, fit.lam_away, fit.error)


async def reference_quotes(
    session: AsyncSession, match_ids: Sequence[int], now: datetime | None = None
) -> dict[int, dict[str, float]]:
    """Dernières cotes du bookmaker de référence : {match: {clé du moteur: cote}}.

    Mêmes règles que les cotes jouables : dernier relevé de chaque sélection, écarté s'il
    est absent du dernier relevé du bookmaker pour ce match (cote retirée) ou trop ancien.
    """
    now = now or datetime.now(UTC)
    if not match_ids:
        return {}
    o = BookmakerOdds
    last = (
        select(func.max(o.id))
        .where(o.match_id.in_(list(match_ids)), o.bookmaker == REFERENCE_BOOKMAKER)
        .group_by(o.match_id, o.bet, o.value)
    )
    latest = (
        select(
            o.match_id, o.bet, o.value, o.price, o.last_seen_at,
            func.max(o.last_seen_at).over(partition_by=o.match_id).label("seen"),
        )
        .where(o.id.in_(last))
        .subquery()
    )  # fmt: skip
    rows = await session.execute(
        select(latest.c.match_id, latest.c.bet, latest.c.value, latest.c.price).where(
            latest.c.last_seen_at >= latest.c.seen,
            latest.c.last_seen_at >= now - REFERENCE_MAX_AGE,
        )
    )
    out: dict[int, dict[str, float]] = {}
    for match_id, bet, value, price in rows:
        mapped = map_bet(bet, value)
        if mapped is not None and mapped[0] in ("1X2", "OU"):
            out.setdefault(match_id, {})["|".join(mapped)] = float(price)
    return out


# Calages déjà faits, par (prévision, cotes de référence) : le calage coûte quelques dizaines
# de millisecondes par match, et rien ne change entre deux relevés de cotes.
_cache: dict[int, tuple[tuple[Any, ...], Calibrated]] = {}
_CACHE_MAX = 5000


def clear_cache() -> None:
    _cache.clear()


async def match_probabilities(
    session: AsyncSession, match_ids: Sequence[int], now: datetime | None = None
) -> dict[int, Calibrated]:
    """Probabilités calées de plusieurs matchs (dernière prévision de chacun)."""
    if not match_ids:
        return {}
    p = MatchPrediction
    preds = await session.execute(
        select(
            p.match_id, p.id, p.created_at, p.lambda_home, p.lambda_away, p.rho, p.share_home,
            p.share_away, p.markets,
        )
        .where(p.match_id.in_(list(match_ids)))
        .order_by(p.match_id, p.run_id.desc())
        .distinct(p.match_id)
    )  # fmt: skip
    quotes = await reference_quotes(session, match_ids, now)
    out: dict[int, Calibrated] = {}
    for match_id, pred_id, made, lam_h, lam_a, rho, share_h, share_a, markets in preds.tuples():
        reference = quotes.get(match_id, {})
        # Avec la date de la prévision : un identifiant peut resservir (base restaurée).
        stamp = (pred_id, made, lam_h, lam_a, tuple(sorted(reference.items())))
        cached = _cache.get(match_id)
        if cached is None or cached[0] != stamp:
            if len(_cache) >= _CACHE_MAX:
                _cache.clear()
            cached = (stamp, calibrate(lam_h, lam_a, rho, share_h, share_a, markets, reference))
            _cache[match_id] = cached
        out[match_id] = cached[1]
    return out
