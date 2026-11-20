"""Alertes de cote (maquette 29 du nouveau visage).

Deux sortes d'alertes, choisies par le joueur :
- sur une sélection : « préviens-moi quand la cote de Köln marque atteint 1,95 » ; une seule
  fois, puis l'alerte s'éteint ;
- d'écart : « dès qu'un pari dépasse la cote de 8 points » (moteur au-dessus de la chance
  donnée par la cote), sur les matchs des prochaines 36 heures, hors sélections nationales
  (leurs écarts n'ont pas tenu en vrai, audit du 18/11/2026).

Au plus une alerte par match ; jamais entre 23 h et 8 h dans le pays du joueur (vérifiée au
passage suivant). La notification constate un fait (cote, chance du moteur) : elle ne propose
jamais de parier.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.accounts.models import User
from footprono.accounts.plans import market_allowed, require_market
from footprono.bookmaker import service
from footprono.bookmaker.live_alerts import quiet, selection_label
from footprono.bookmaker.play_models import OddsAlert, OddsAlertHit
from footprono.core.errors import AppError, NotFoundError
from footprono.football.models import Competition, Match, MatchStatus, Season, Team
from footprono.ingestion.reference import NATIONS_BY_CODE
from footprono.notifications import service as notifications

MAX_ALERTS = 30
GAPS = (0.05, 0.08, 0.10)
AHEAD = timedelta(hours=36)
KIND = "odds_alert"
DASH = "\u2013"  # tiret demi-cadratin entre les deux équipes


def _odds(v: Decimal | float | None) -> str:
    return "—" if v is None else f"{Decimal(str(v)):.2f}".replace(".", ",")


async def _match_names(session: AsyncSession, match_ids: list[int]) -> dict[int, Any]:
    if not match_ids:
        return {}
    home, away = Team.__table__.alias("home"), Team.__table__.alias("away")
    rows = (
        await session.execute(
            select(
                Match.id, Match.kickoff_at, Match.status, Competition.code, home.c.name, away.c.name
            )
            .join(Season, Season.id == Match.season_id)
            .join(Competition, Competition.id == Season.competition_id)
            .join(home, home.c.id == Match.home_team_id)
            .join(away, away.c.id == Match.away_team_id)
            .where(Match.id.in_(match_ids))
        )
    ).all()
    return {r[0]: r for r in rows}


def _open(row: Any, now: datetime) -> bool:
    return row[2] is MatchStatus.SCHEDULED and row[1] is not None and row[1] > now


async def create_selection(
    session: AsyncSession,
    user: User,
    match_id: int,
    market: str,
    line: str,
    selection: str,
    target_odds: Decimal,
    now: datetime | None = None,
) -> OddsAlert:
    now = now or datetime.now(UTC)
    require_market(user, market, now)
    info = (await _match_names(session, [match_id])).get(match_id)
    if info is None:
        raise NotFoundError("match introuvable")
    if not _open(info, now):
        raise AppError("match déjà commencé ou terminé : plus d'alerte possible")
    k = service.key(market, line, selection)
    offer = (await service.match_offer(session, match_id, now)).get(k)
    if offer is None:
        raise AppError("pas de cote récente pour cette sélection")
    if target_odds <= offer.odds:
        raise AppError(f"la cote est déjà à {_odds(offer.odds)} : choisir une cote plus haute")
    existing = await session.scalar(
        select(OddsAlert).where(
            OddsAlert.user_id == user.id,
            OddsAlert.kind == "selection",
            OddsAlert.match_id == match_id,
            OddsAlert.market == market,
            OddsAlert.line == line,
            OddsAlert.selection == selection,
            OddsAlert.triggered_at.is_(None),
        )
    )
    if existing is not None:
        existing.target_odds = target_odds
        existing.active = True
        await session.flush()
        return existing
    await _check_count(session, user.id)
    alert = OddsAlert(
        user_id=user.id,
        kind="selection",
        match_id=match_id,
        market=market,
        line=line,
        selection=selection,
        target_odds=target_odds,
        start_odds=offer.odds,
        active=True,
    )
    session.add(alert)
    await session.flush()
    return alert


async def set_gap(session: AsyncSession, user: User, min_gap: float, active: bool) -> OddsAlert:
    """L'alerte d'écart (une par joueur) : créée ou réglée."""
    if not any(abs(min_gap - g) < 1e-9 for g in GAPS):
        raise AppError("écart de 5, 8 ou 10 points")
    alert = await session.scalar(
        select(OddsAlert).where(OddsAlert.user_id == user.id, OddsAlert.kind == "gap")
    )
    if alert is None:
        await _check_count(session, user.id)
        alert = OddsAlert(user_id=user.id, kind="gap")
        session.add(alert)
    alert.min_gap = min_gap
    alert.active = active
    await session.flush()
    return alert


async def _check_count(session: AsyncSession, user_id: int) -> None:
    n = len(
        (
            await session.scalars(
                select(OddsAlert.id).where(OddsAlert.user_id == user_id, OddsAlert.active)
            )
        ).all()
    )
    if n >= MAX_ALERTS:
        raise AppError(f"{MAX_ALERTS} alertes actives au plus : en retirer une d'abord")


async def _own(session: AsyncSession, user: User, alert_id: int) -> OddsAlert:
    alert = await session.get(OddsAlert, alert_id)
    if alert is None or alert.user_id != user.id:
        raise NotFoundError("alerte introuvable")
    return alert


async def set_active(session: AsyncSession, user: User, alert_id: int, active: bool) -> OddsAlert:
    alert = await _own(session, user, alert_id)
    if active and alert.kind == "selection" and alert.triggered_at is not None:
        raise AppError("alerte déjà déclenchée : en créer une nouvelle")
    alert.active = active
    await session.flush()
    return alert


async def remove(session: AsyncSession, user: User, alert_id: int) -> None:
    alert = await _own(session, user, alert_id)
    await session.execute(delete(OddsAlert).where(OddsAlert.id == alert.id))
    await session.flush()


async def listing(session: AsyncSession, user: User, now: datetime | None = None) -> dict[str, Any]:
    """Mes alertes (avec la cote et la chance du moteur du moment) et les déclenchements des
    sept derniers jours."""
    now = now or datetime.now(UTC)
    alerts = (
        await session.scalars(
            select(OddsAlert).where(OddsAlert.user_id == user.id).order_by(OddsAlert.id.desc())
        )
    ).all()
    hits = (
        await session.scalars(
            select(OddsAlertHit)
            .where(
                OddsAlertHit.user_id == user.id, OddsAlertHit.created_at >= now - timedelta(days=7)
            )
            .order_by(OddsAlertHit.created_at.desc())
            .limit(20)
        )
    ).all()
    ids = list({a.match_id for a in alerts if a.match_id} | {h.match_id for h in hits})
    names = await _match_names(session, ids)
    open_ids = [m for m, r in names.items() if _open(r, now)]
    offers, probs = await service.cached_offers_and_probabilities(session, open_ids, now)

    def match(mid: int) -> dict[str, Any]:
        r = names.get(mid)
        return {
            "match_id": mid,
            "home": r[4] if r else "",
            "away": r[5] if r else "",
            "competition": r[3] if r else "",
            "kickoff_at": r[1] if r else None,
            "open": bool(r) and _open(r, now),
        }

    out_alerts = []
    gap = None
    for a in alerts:
        if a.kind == "gap":
            gap = {"id": a.id, "min_gap": a.min_gap, "active": a.active}
            continue
        assert a.match_id is not None
        assert a.market is not None
        k = service.key(a.market, a.line or "", a.selection or "")
        offer = offers.get(a.match_id, {}).get(k)
        m = match(a.match_id)
        out_alerts.append(
            m
            | {
                "id": a.id,
                "market": a.market,
                "line": a.line or "",
                "selection": a.selection,
                "label": selection_label(
                    a.market, a.line or "", a.selection or "", m["home"], m["away"]
                ),
                "target_odds": a.target_odds,
                "start_odds": a.start_odds,
                "odds": offer.odds if offer else None,
                "engine": probs.get(a.match_id, {}).get(k),
                "active": a.active and a.triggered_at is None and m["open"],
                "triggered_at": a.triggered_at,
            }
        )
    out_hits = []
    for h in hits:
        m = match(h.match_id)
        k = service.key(h.market, h.line, h.selection)
        offer = offers.get(h.match_id, {}).get(k)
        out_hits.append(
            m
            | {
                "id": h.id,
                "alert_id": h.alert_id,
                "market": h.market,
                "line": h.line,
                "selection": h.selection,
                "label": selection_label(h.market, h.line, h.selection, m["home"], m["away"]),
                "from_odds": h.from_odds,
                "odds": h.odds,
                "current_odds": offer.odds if offer else None,
                "engine": h.engine,
                "implied": round(1 / float(h.odds), 4),
                "at": h.created_at,
            }
        )
    return {"alerts": out_alerts, "gap": gap, "hits": out_hits, "gaps": list(GAPS)}


async def check(session: AsyncSession, now: datetime | None = None) -> int:
    """Passe sur les alertes actives ; enregistre les déclenchements et leurs notifications.
    Renvoie le nombre de notifications créées (diffusées ensuite par ``publish_pending``)."""
    now = now or datetime.now(UTC)
    alerts = (await session.scalars(select(OddsAlert).where(OddsAlert.active))).all()
    if not alerts:
        return 0
    users = {
        u.id: u
        for u in await session.scalars(
            select(User).where(User.id.in_({a.user_id for a in alerts}), User.is_active)
        )
    }
    alerts = [a for a in alerts if a.user_id in users and not quiet(users[a.user_id].country, now)]
    sent = 0
    sel_alerts = [a for a in alerts if a.kind == "selection" and a.triggered_at is None]
    gap_alerts = [a for a in alerts if a.kind == "gap" and a.min_gap]
    match_ids = {a.match_id for a in sel_alerts if a.match_id}
    upcoming: list[int] = []
    if gap_alerts:
        upcoming = list(
            (
                await session.scalars(
                    select(Match.id)
                    .join(Season, Season.id == Match.season_id)
                    .join(Competition, Competition.id == Season.competition_id)
                    .where(
                        Match.status == MatchStatus.SCHEDULED,
                        Match.kickoff_at > now,
                        Match.kickoff_at <= now + AHEAD,
                        Competition.code.not_in(list(NATIONS_BY_CODE)),
                    )
                )
            ).all()
        )
    ids = list(match_ids | set(upcoming))
    if not ids:
        return 0
    names = await _match_names(session, ids)
    offers = await service.match_offers(session, ids, now)
    probs = await service.models_probabilities(session, ids)

    for a in sel_alerts:
        assert a.match_id is not None
        assert a.market is not None
        assert a.target_odds is not None
        r = names.get(a.match_id)
        if r is None or not _open(r, now):
            a.active = False  # match commencé : l'alerte n'a plus d'objet
            continue
        user = users[a.user_id]
        if not market_allowed(user, a.market, now):
            continue
        k = service.key(a.market, a.line or "", a.selection or "")
        offer = offers.get(a.match_id, {}).get(k)
        p = probs.get(a.match_id, {}).get(k)
        if offer is None or p is None or offer.odds < a.target_odds:
            continue
        hit = await _hit(session, a, a.match_id, offer, p, a.start_odds)
        if hit is None:
            continue
        a.triggered_at = now
        a.active = False
        label = selection_label(a.market, a.line or "", a.selection or "", r[4], r[5])
        notifications.add(
            session,
            a.user_id,
            KIND,
            "Alerte de cote atteinte",
            f"{r[4]} {DASH} {r[5]} · {label} : cote {_odds(a.start_odds)} → {_odds(offer.odds)}. "
            f"Chance du moteur : {round(p * 100)} %.",
            {"screen": "odds_alerts", "match_id": a.match_id},
        )
        sent += 1

    for a in gap_alerts:
        user = users[a.user_id]
        done = set(
            (
                await session.scalars(
                    # Au plus une alerte par match pour un joueur, toutes alertes confondues.
                    select(OddsAlertHit.match_id).where(OddsAlertHit.user_id == a.user_id)
                )
            ).all()
        )
        found = []
        for mid in upcoming:
            if mid in done or mid not in names:
                continue
            best = None
            for k, offer in offers.get(mid, {}).items():
                p = probs.get(mid, {}).get(k)
                if p is None or offer.odds <= 1 or not market_allowed(user, offer.market, now):
                    continue
                gap = p - 1 / float(offer.odds)
                if gap >= (a.min_gap or 1) and (best is None or gap > best[0]):
                    best = (gap, offer, p)
            if best is not None:
                found.append((mid, *best))
        new = []
        for mid, gap, offer, p in sorted(found, key=lambda x: -x[1]):
            if await _hit(session, a, mid, offer, p, None) is not None:
                new.append((mid, gap, offer, p))
        if not new:
            continue
        a.triggered_at = now
        mid, gap, offer, p = new[0]
        r = names[mid]
        label = selection_label(offer.market, offer.line, offer.selection, r[4], r[5])
        others = len(new) - 1
        plural = "s" if others > 1 else ""
        more = f" (et {others} autre{plural} match{plural})" if others else ""
        notifications.add(
            session,
            a.user_id,
            KIND,
            f"Moteur au-dessus de la cote de {round(gap * 100)} points",
            f"{r[4]} {DASH} {r[5]} · {label} : moteur {round(p * 100)} %, "
            f"cote {_odds(offer.odds)} ({round(100 / float(offer.odds))} %){more}.",
            {"screen": "odds_alerts", "match_id": mid},
        )
        sent += 1
    await session.commit()
    return sent


async def _hit(
    session: AsyncSession,
    alert: OddsAlert,
    match_id: int,
    offer: service.Offer,
    p: float,
    from_odds: Decimal | None,
) -> OddsAlertHit | None:
    """Enregistre le déclenchement ; None si cette alerte a déjà sonné pour ce match."""
    exists = await session.scalar(
        select(OddsAlertHit.id).where(
            OddsAlertHit.alert_id == alert.id, OddsAlertHit.match_id == match_id
        )
    )
    if exists is not None:
        return None
    hit = OddsAlertHit(
        alert_id=alert.id,
        user_id=alert.user_id,
        match_id=match_id,
        market=offer.market,
        line=offer.line,
        selection=offer.selection,
        from_odds=from_odds,
        odds=offer.odds,
        bookmaker=offer.bookmaker,
        engine=round(p, 4),
    )
    session.add(hit)
    await session.flush()
    return hit
