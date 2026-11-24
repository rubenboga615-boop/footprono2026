"""Tableau de bord « Aujourd'hui » (nouveau visage, étape B, plan du 20/11/2026).

Seulement ce qui n'existe pas déjà ailleurs : la courbe du solde (mouvements du
portefeuille), le bilan des 30 derniers jours, le moteur annoncé contre réalisé, les mises
de la semaine, et les sélections du jour où le moteur dépasse la cote d'au moins 3 points
(hors sélections nationales et coupes d'Europe, et jamais plus de 15 points : voir GAP_MAX).
Les paris en cours, la montante et les coupons du jour viennent de leurs propres routes.
On informe, on ne pousse jamais à parier.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.accounts.models import User, Wallet, WalletEntry
from footprono.accounts.plans import market_allowed
from footprono.bookmaker import play_plan, service
from footprono.bookmaker.models import Bet, BetSelection
from footprono.bookmaker.record import _group
from footprono.football.models import Competition, Match, MatchStatus, Season, Team
from footprono.ingestion.reference import UNMEASURED_CODES as _UNMEASURED

GAP_MIN = 0.03  # 3 points, comme la pastille « moteur contre cote »
# Au-delà, l'écart est bien plus probablement une erreur du moteur qu'une occasion (vérification
# du 24/11/2026 : Bruges à 50 % contre Liverpool, cote 4,72) : jamais montré comme occasion.
GAP_MAX = 0.15
OCCASIONS_SHOWN = False
# Compétitions où l'« annoncé contre réalisé » face à la cote n'est pas mesuré ou est mauvais :
# sélections nationales (audit du 18/11) et coupes d'Europe (clubs de championnats différents,
# vérification du 24/11/2026). Jamais d'occasion ni d'alerte d'écart sur leurs matchs.
UNMEASURED_CODES = sorted(_UNMEASURED)
ABOVE_LIMIT = 6
ABOVE_AHEAD = timedelta(hours=36)


async def _curve(session: AsyncSession, user_id: int) -> list[dict[str, Any]]:
    """Solde en fin de journée (UTC), un point par jour où il a bougé."""
    day = func.date(func.timezone("UTC", WalletEntry.created_at))
    rows = (
        await session.execute(
            select(day, WalletEntry.balance_after)
            .where(WalletEntry.user_id == user_id)
            .distinct(day)
            .order_by(day, WalletEntry.created_at.desc(), WalletEntry.id.desc())
        )
    ).all()
    return [{"day": d.isoformat(), "balance": int(b)} for d, b in rows]


async def _last_30(session: AsyncSession, user_id: int, now: datetime) -> dict[str, Any]:
    since = now - timedelta(days=30)
    row = (
        await session.execute(
            select(
                func.count(Bet.id),
                func.count(Bet.id).filter(Bet.outcome.in_(("won", "partial"))),
                func.coalesce(func.sum(Bet.stake), 0),
                func.coalesce(func.sum(Bet.payout), 0),
            ).where(
                Bet.user_id == user_id,
                Bet.status == "settled",
                Bet.outcome != "push",
                Bet.settled_at >= since,
            )
        )
    ).one()
    settled, won, staked, returned = (int(x) for x in row)
    return {
        "settled": settled,
        "won": won,
        "staked": staked,
        "returned": returned,
        "yield": None if staked == 0 else round((returned - staked) / staked, 4),
    }


async def _engine(session: AsyncSession, user_id: int) -> dict[str, Any]:
    """Chance moyenne annoncée par le moteur sur mes sélections réglées, contre la part
    réellement gagnée (demi-gains compris, remboursées exclues)."""
    row = (
        await session.execute(
            select(
                func.count(BetSelection.id),
                func.avg(BetSelection.model_probability),
                func.count(BetSelection.id).filter(BetSelection.result.in_(("win", "half_win"))),
            )
            .join(Bet, Bet.id == BetSelection.bet_id)
            .where(
                Bet.user_id == user_id,
                BetSelection.model_probability.is_not(None),
                BetSelection.result.in_(("win", "half_win", "loss", "half_loss")),
            )
        )
    ).one()
    n, announced, won = int(row[0]), row[1], int(row[2])
    return {
        "selections": n,
        "announced": None if n == 0 else round(float(announced), 4),
        "observed": None if n == 0 else round(won / n, 4),
    }


async def _stakes(session: AsyncSession, user: User, now: datetime) -> dict[str, int]:
    # Même semaine que le plan de jeu : depuis lundi 0 h dans le pays du joueur (vérification
    # du 24/11/2026 : 7 jours glissants ici, semaine civile là, deux montants différents).
    week = play_plan.week_start(user.country, now)
    row = (
        await session.execute(
            select(
                func.coalesce(func.sum(Bet.stake).filter(Bet.placed_at >= week), 0),
                func.coalesce(
                    func.sum(Bet.stake).filter(
                        Bet.placed_at >= week - timedelta(days=7), Bet.placed_at < week
                    ),
                    0,
                ),
            ).where(Bet.user_id == user.id)
        )
    ).one()
    return {"week": int(row[0]), "previous_week": int(row[1])}


async def _markets_30(session: AsyncSession, user_id: int, now: datetime) -> list[dict[str, Any]]:
    """« Où le moteur tient parole (30 j) » : par marché, chance annoncée contre part gagnée
    de mes sélections des paris réglés ces 30 derniers jours (comme « Mon bilan »)."""
    rows = (
        await session.execute(
            select(BetSelection.market, BetSelection.result, BetSelection.model_probability)
            .join(Bet, Bet.id == BetSelection.bet_id)
            .where(
                Bet.user_id == user_id,
                Bet.status == "settled",
                Bet.settled_at >= now - timedelta(days=30),
                BetSelection.result != "pending",
            )
        )
    ).all()
    return _group([(m, r, p) for m, r, p in rows])


async def engine_above_odds(
    session: AsyncSession, user: User, now: datetime, limit: int = ABOVE_LIMIT
) -> list[dict[str, Any]]:
    """Sélections des prochaines 36 heures où le moteur dépasse la cote d'au moins 3 points,
    les plus grands écarts d'abord ; marchés de la formule du joueur ; jamais les sélections
    nationales."""
    home, away = Team.__table__.alias("home"), Team.__table__.alias("away")
    rows = (
        await session.execute(
            select(Match.id, Match.kickoff_at, Competition.code, home.c.name, away.c.name)
            .join(Season, Season.id == Match.season_id)
            .join(Competition, Competition.id == Season.competition_id)
            .join(home, home.c.id == Match.home_team_id)
            .join(away, away.c.id == Match.away_team_id)
            .where(
                Match.status == MatchStatus.SCHEDULED,
                Match.kickoff_at > now,
                Match.kickoff_at <= now + ABOVE_AHEAD,
                Competition.code.not_in(UNMEASURED_CODES),
            )
            .order_by(Match.kickoff_at)
            .limit(80)
        )
    ).all()
    if not rows:
        return []
    info = {r[0]: r for r in rows}
    offers, probs = await service.cached_offers_and_probabilities(session, list(info))
    found = []
    for mid, by_key in offers.items():
        for key, offer in by_key.items():
            p = probs.get(mid, {}).get(key)
            if p is None or offer.odds <= 1 or not market_allowed(user, offer.market, now):
                continue
            implied = 1 / float(offer.odds)
            if not GAP_MIN <= p - implied <= GAP_MAX:
                continue
            _, kickoff, code, h, a = info[mid]
            found.append(
                {
                    "match_id": mid,
                    "kickoff_at": kickoff,
                    "competition": code,
                    "home": h,
                    "away": a,
                    "market": offer.market,
                    "line": offer.line or None,
                    "selection": offer.selection,
                    "odds": offer.odds,
                    "bookmaker": offer.bookmaker,
                    "engine": round(p, 4),
                    "implied": round(implied, 4),
                }
            )
    found.sort(key=lambda x: -(x["engine"] - x["implied"]))
    # Un seul écart par match : la liste montre des matchs différents.
    seen: set[int] = set()
    out = []
    for f in found:
        if f["match_id"] in seen:
            continue
        seen.add(f["match_id"])
        out.append(f)
        if len(out) == limit:
            break
    return out


async def dashboard(
    session: AsyncSession, user: User, now: datetime | None = None
) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    wallet = await session.get(Wallet, user.id)
    return {
        "balance": wallet.balance if wallet else 0,
        "currency": user.currency,
        "curve": await _curve(session, user.id),
        "last_30_days": await _last_30(session, user.id, now),
        "engine": await _engine(session, user.id),
        "markets_30": await _markets_30(session, user.id, now),
        "stakes": await _stakes(session, user, now),
        # Occasions cachées aux joueurs (décision du 24/11/2026, principe n° 4 : rien de tel
        # sans preuve) ; ``engine_above_odds`` reste pour les mesurer.
        "engine_above_odds": await engine_above_odds(session, user, now) if OCCASIONS_SHOWN else [],
        # Mon plan de jeu (maquette 30) : budget et mises de la semaine (lundi 0 h).
        "play_plan": await play_plan.summary(session, user, now),
        "gap_min": GAP_MIN,
    }
