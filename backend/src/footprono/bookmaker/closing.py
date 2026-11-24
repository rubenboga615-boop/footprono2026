"""Cote de clôture et mesure en silence (plan qualité du 24/11/2026, étape 2).

La **cote de clôture** est la dernière cote relevée chez le bookmaker avant le coup d'envoi :
le marché y a intégré toutes les informations (compositions, blessures). Battre la clôture en
moyenne sur des centaines de sélections est la seule preuve qu'une méthode bat le bookmaker ;
la réussite seule dépend trop du hasard sur quelques dizaines de paris.

Ce module :
- garde la clôture et le résultat de chaque sélection proposée ou jouée : coupons du jour,
  paris des joueurs, alertes de cote déclenchées, « occasions » ;
- enregistre en silence les « occasions » (moteur au-dessus de la cote d'au moins 3 points),
  cachées aux joueurs, **toutes compétitions comprises** (coupes d'Europe et sélections aussi :
  c'est justement ce qu'il faut mesurer) ;
- fait le bilan par tranche d'écart, compétition et marché, à 1 000 F par sélection.

Limite connue : les cotes sont relevées toutes les 3 heures, plus un relevé des matchs proposés
peu avant le coup d'envoi (``closing_targets``). La « clôture » est donc la dernière cote vue
avant le match, à quelques dizaines de minutes près.
"""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.bookmaker import service, settlement
from footprono.bookmaker.models import Bet, BetSelection
from footprono.bookmaker.play_models import OddsAlertHit, SilentPick
from footprono.bookmaker.smart_models import SmartCoupon
from footprono.football.models import BookmakerOdds, Competition, Match, MatchStatus, Season
from footprono.ingestion.sources.api_football_odds import map_bet

STAKE = 1000  # F par sélection dans les bilans
GAP_MIN = 0.03  # 3 points : même seuil que la pastille « moteur contre cote »
AHEAD = timedelta(hours=36)  # matchs dont les occasions sont enregistrées
SOURCE_OCCASION = "occasion"
# Tranches d'écart (moteur - cote, en points) des bilans.
BANDS = ((3, 5), (5, 10), (10, 15), (15, None))


def band_of(gap_points: float) -> str:
    for lo, hi in BANDS:
        if gap_points >= lo and (hi is None or gap_points < hi):
            return f"+{lo} pts et plus" if hi is None else f"+{lo} à +{hi} pts"
    return "moins de +3 pts"


# ------------------------------------------------------------------ cote de clôture


async def closing_prices(
    session: AsyncSession, match_id: int, bookmaker: str, kickoff: datetime
) -> dict[str, Decimal]:
    """{clé de marché: dernière cote relevée avant le coup d'envoi} chez ce bookmaker."""
    rows = (
        await session.execute(
            select(BookmakerOdds.bet, BookmakerOdds.value, BookmakerOdds.price)
            .where(
                BookmakerOdds.match_id == match_id,
                BookmakerOdds.bookmaker == bookmaker,
                BookmakerOdds.fetched_at <= kickoff,
            )
            .order_by(BookmakerOdds.fetched_at, BookmakerOdds.id)
        )
    ).all()
    out: dict[str, Decimal] = {}
    for bet, value, price in rows:
        mapped = map_bet(bet, value)
        if mapped is not None:
            out[service.key(*mapped)] = price  # le plus récent l'emporte
    return out


class _Closings:
    """Clôtures lues une fois par (match, bookmaker)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.cache: dict[tuple[int, str], dict[str, Decimal]] = {}

    async def get(
        self, match: Match, bookmaker: str, market: str, line: str | None, selection: str
    ) -> Decimal | None:
        if match.kickoff_at is None:
            return None
        k = (match.id, bookmaker)
        if k not in self.cache:
            self.cache[k] = await closing_prices(
                self.session, match.id, bookmaker, match.kickoff_at
            )
        return self.cache[k].get(service.key(market, line or "", selection))


def _started(match: Match, now: datetime) -> bool:
    return match.kickoff_at is not None and match.kickoff_at <= now


async def _grade(
    session: AsyncSession, match_id: int, market: str, line: str, selection: str, odds: Decimal,
    now: datetime,
) -> str | None:  # fmt: skip
    probe = BetSelection(
        match_id=match_id, market=market, line=line, selection=selection, odds=odds
    )
    grade = await settlement.grade_selection(session, probe, now)
    return grade.result if grade else None


async def fill(session: AsyncSession, now: datetime | None = None) -> dict[str, int]:
    """Clôture (et résultat, pour ce qui n'a pas de règlement propre) des sélections dont le
    match a commencé. Chaque sélection n'est cherchée qu'une fois (``closing_checked_at``)."""
    now = now or datetime.now(UTC)
    closings = _Closings(session)
    report = {"bets": 0, "daily_coupons": 0, "alerts": 0, "occasions": 0, "graded": 0}

    async def matches(ids: Iterable[int]) -> dict[int, Match]:
        ids = list(set(ids))
        if not ids:
            return {}
        rows = await session.scalars(select(Match).where(Match.id.in_(ids)))
        return {m.id: m for m in rows.all()}

    # Paris des joueurs.
    sels = (
        await session.scalars(
            select(BetSelection)
            .join(Match, Match.id == BetSelection.match_id)
            .where(BetSelection.closing_checked_at.is_(None), Match.kickoff_at <= now)
            .limit(5000)
        )
    ).all()
    by_id = await matches(s.match_id for s in sels)
    for s in sels:
        m = by_id[s.match_id]
        s.closing_odds = await closings.get(m, s.bookmaker, s.market, s.line, s.selection)
        s.closing_checked_at = now
        report["bets"] += 1

    # Coupons du jour (moteur 1) : clôture rangée dans chaque sélection.
    coupons = (
        await session.scalars(
            select(SmartCoupon).where(
                SmartCoupon.engine == 1, SmartCoupon.day >= (now - timedelta(days=60)).date()
            )
        )
    ).all()
    by_id = await matches(sel["match_id"] for c in coupons for sel in c.selections)
    for c in coupons:
        changed = False
        selections = []
        for sel in c.selections:
            got = by_id.get(sel["match_id"])
            if got is not None and "closing_odds" not in sel and _started(got, now):
                price = await closings.get(
                    got, sel["bookmaker"], sel["market"], sel.get("line"), sel["selection"]
                )
                sel = {**sel, "closing_odds": None if price is None else str(price)}
                changed = True
                report["daily_coupons"] += 1
            selections.append(sel)
        if changed:
            c.selections = selections  # nouvelle liste : la colonne JSON est réécrite

    # Alertes de cote déclenchées, puis occasions : clôture et résultat.
    for model, name in ((OddsAlertHit, "alerts"), (SilentPick, "occasions")):
        rows: Sequence[Any] = (
            await session.scalars(
                select(model).where((model.closing_checked_at.is_(None)) | (model.result.is_(None)))
            )
        ).all()
        by_id = await matches(r.match_id for r in rows)
        for r in rows:
            m = by_id[r.match_id]
            if not _started(m, now):
                continue
            if r.closing_checked_at is None:
                r.closing_odds = await closings.get(m, r.bookmaker, r.market, r.line, r.selection)
                r.closing_checked_at = now
                report[name] += 1
            if r.result is None and m.status in (MatchStatus.FINISHED, MatchStatus.CANCELLED):
                r.result = await _grade(
                    session, r.match_id, r.market, r.line or "", r.selection, r.odds, now
                )
                report["graded"] += r.result is not None
    await session.commit()
    return report


# ------------------------------------------------------------------ occasions en silence


async def record_occasions(session: AsyncSession, now: datetime | None = None) -> int:
    """Enregistre la meilleure « occasion » (plus grand écart moteur - cote, d'au moins
    3 points) de chaque match des 36 prochaines heures, toutes compétitions comprises. Une
    seule fois par match et par sélection : la cote gardée est celle du premier relevé."""
    now = now or datetime.now(UTC)
    rows = (
        await session.execute(
            select(Match.id, Competition.code)
            .join(Season, Season.id == Match.season_id)
            .join(Competition, Competition.id == Season.competition_id)
            .where(
                Match.status == MatchStatus.SCHEDULED,
                Match.kickoff_at > now,
                Match.kickoff_at <= now + AHEAD,
            )
        )
    ).all()
    if not rows:
        return 0
    code: dict[int, str] = {mid: c for mid, c in rows}
    offers, probs = await service.cached_offers_and_probabilities(session, list(code))
    existing = {
        (r.match_id, r.market, r.line, r.selection)
        for r in (
            await session.scalars(
                select(SilentPick).where(
                    SilentPick.source == SOURCE_OCCASION, SilentPick.match_id.in_(list(code))
                )
            )
        ).all()
    }
    added = 0
    for mid, by_key in offers.items():
        best: tuple[float, service.Offer, float] | None = None
        for k, offer in by_key.items():
            p = probs.get(mid, {}).get(k)
            if p is None or offer.odds <= 1:
                continue
            gap = p - 1 / float(offer.odds)
            if gap >= GAP_MIN and (best is None or gap > best[0]):
                best = (gap, offer, p)
        if best is None:
            continue
        _, offer, p = best
        line = offer.line or ""
        if (mid, offer.market, line, offer.selection) in existing:
            continue
        session.add(
            SilentPick(
                source=SOURCE_OCCASION,
                day=now.date(),
                match_id=mid,
                competition=code[mid],
                market=offer.market,
                line=line,
                selection=offer.selection,
                bookmaker=offer.bookmaker,
                odds=offer.odds,
                engine=round(p, 4),
            )
        )
        added += 1
    await session.commit()
    return added


# ------------------------------------------------------------------ bilans


def _payout(result: str, odds: float) -> float:
    """Retour pour 1 F misé : gagné = cote ; demi-gain = (1 + cote) / 2 ; remboursé = 1."""
    if result == "win":
        return odds
    if result == "half_win":
        return (1 + odds) / 2
    if result in ("push", "void"):
        return 1.0
    if result == "half_loss":
        return 0.5
    return 0.0


def _summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Réglées, gagnées, chance annoncée et réalisée, gain à 1 000 F, part qui bat la clôture."""
    settled = [i for i in items if i["result"] not in (None, "pending", "push", "void")]
    n = len(settled)
    won = sum(i["result"] in ("win", "half_win") for i in settled)
    profit = sum(STAKE * (_payout(i["result"], i["odds"]) - 1) for i in settled)
    with_close = [i for i in items if i.get("closing") is not None]
    beat = sum(i["odds"] > i["closing"] for i in with_close)
    return {
        "selections": len(items),
        "settled": n,
        "won": won,
        "announced": round(sum(i["engine"] for i in settled) / n, 4) if n else None,
        "observed": round(won / n, 4) if n else None,
        "profit": round(profit),
        "yield": round(profit / (STAKE * n), 4) if n else None,
        "with_closing": len(with_close),
        "beat_closing": round(beat / len(with_close), 4) if with_close else None,
    }


def _grouped(items: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {"total": _summary(items)}
    for field in ("band", "competition", "market"):
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for i in items:
            groups[i[field]].append(i)
        out[f"by_{field}"] = {k: _summary(v) for k, v in sorted(groups.items())}
    return out


async def report(
    session: AsyncSession, now: datetime | None = None, days: int = 30
) -> dict[str, Any]:
    """Bilans des 30 derniers jours (console) : occasions, alertes, coupons du jour, paris."""
    now = now or datetime.now(UTC)
    since = now - timedelta(days=days)
    rows = (
        await session.execute(
            select(Match.id, Competition.code)
            .join(Season, Season.id == Match.season_id)
            .join(Competition, Competition.id == Season.competition_id)
            .where(Match.kickoff_at >= since)
        )
    ).all()
    comp: dict[int, str] = {mid: code for mid, code in rows}

    def item(match_id: int, market: str, odds: Decimal, engine: float | None,
             closing: Decimal | None, result: str | None) -> dict[str, Any]:  # fmt: skip
        o = float(odds)
        gap = ((engine or 0) - 1 / o) * 100
        return {
            "competition": comp.get(match_id, "?"),
            "market": market,
            "band": band_of(gap),
            "odds": o,
            "engine": engine or 0.0,
            "closing": None if closing is None else float(closing),
            "result": result,
        }

    occasions = [
        item(r.match_id, r.market, r.odds, r.engine, r.closing_odds, r.result)
        for r in (await session.scalars(select(SilentPick).where(SilentPick.created_at >= since)))
    ]
    alerts = [
        item(r.match_id, r.market, r.odds, r.engine, r.closing_odds, r.result)
        for r in (
            await session.scalars(select(OddsAlertHit).where(OddsAlertHit.created_at >= since))
        )
    ]
    daily = [
        item(
            s["match_id"], s["market"], Decimal(s["odds"]), s.get("model_probability"),
            None if s.get("closing_odds") is None else Decimal(s["closing_odds"]),
            {"won": "win", "lost": "loss"}.get(s.get("result", ""), s.get("result")),
        )
        for c in (
            await session.scalars(
                select(SmartCoupon).where(SmartCoupon.engine == 1, SmartCoupon.day >= since.date())
            )
        )
        for s in c.selections
    ]  # fmt: skip
    bets = [
        item(s.match_id, s.market, s.odds, s.model_probability, s.closing_odds, s.result)
        for s in (
            await session.scalars(
                select(BetSelection)
                .join(Bet, Bet.id == BetSelection.bet_id)
                .where(Bet.placed_at >= since)
            )
        )
    ]
    return {
        "days": days,
        "stake": STAKE,
        "occasions": _grouped(occasions),
        "alerts": _grouped(alerts),
        "daily_coupon_selections": _grouped(daily),
        "player_bets": _grouped(bets),
    }
