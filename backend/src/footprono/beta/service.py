"""Mode bêta (FP_BETA_SHARING) : partage anonyme et volontaire pendant la période de test.

Règles (maquette validée le 06/11/2026) :
- éteint par défaut ; le joueur l'allume lui-même (profil) après avoir lu ce qui est
  partagé ; il peut l'éteindre à tout moment : ses événements sont alors effacés ;
- un testeur n'est qu'un numéro (« Testeur n° 12 ») : ni nom, ni numéro de téléphone,
  ni e-mail, ni paiement ne sortent du serveur (Observatoire, export) ;
- réglage coupé (fin de la période de test) : plus rien n'est collecté ; « Tout effacer »
  (console) supprime les événements et les numéros de testeur.
"""

import re
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.accounts.models import BetaEvent, User
from footprono.bookmaker.models import Bet, BetSelection
from footprono.bookmaker.montante_models import Montante
from footprono.engine.audit import family_of

KINDS = ("error", "slow", "timing", "action")
MAX_EVENTS = 50  # par envoi de l'application
MAX_PER_DAY = 2000  # par testeur : une application qui boucle ne remplit pas la base
SLOW_MS = 20_000  # au-delà : « attente dépassée » (délai normal de l'application)
WINDOW = timedelta(days=7)

# Adresses de l'API → nom de l'écran, pour l'Observatoire.
SCREENS = (
    ("/smart-coupon", "Coupon intelligent"),
    ("/montantes/{id}/suggestions", "Suggestions de montante"),
    ("/montantes", "Montante"),
    ("/reliability", "Fiabilité"),
    ("/matches/{id}/offer", "Cotes d'un match"),
    ("/matches/{id}", "Fiche match"),
    ("/predictions/upcoming", "Liste des matchs"),
    ("/bets", "Bookmaker"),
    ("/smart-coupons/day", "Coupons du jour"),
)


def clean_path(path: str) -> str:
    """Adresse sans identifiant ni paramètre (« /matches/123/offer » → « /matches/{id}/offer »)."""
    path = path.split("?", 1)[0].removeprefix("/api/v1")
    return re.sub(r"/\d+", "/{id}", path)[:128]


def screen_of(path: str) -> str:
    for prefix, name in SCREENS:
        if path == prefix or (path.startswith(prefix + "/") and "{id}" not in prefix):
            return name
    return path


async def set_sharing(session: AsyncSession, user: User, enabled: bool) -> dict[str, Any]:
    """Allume ou éteint le partage ; éteint, les événements du testeur sont effacés."""
    if enabled and user.beta_number is None:
        user.beta_number = (await session.scalar(select(func.max(User.beta_number))) or 0) + 1
    if not enabled and user.beta_number is not None:
        await session.execute(delete(BetaEvent).where(BetaEvent.beta_number == user.beta_number))
    user.beta_sharing = enabled
    await session.commit()
    return {"enabled": enabled, "tester": user.beta_number if enabled else None}


async def record(session: AsyncSession, user: User, events: list[dict[str, Any]]) -> int:
    """Enregistre les événements envoyés par l'application d'un testeur volontaire."""
    if not user.beta_sharing or user.beta_number is None:
        return 0
    today = await session.scalar(
        select(func.count())
        .select_from(BetaEvent)
        .where(
            BetaEvent.beta_number == user.beta_number,
            BetaEvent.created_at >= datetime.now(UTC) - timedelta(days=1),
        )
    )
    if (today or 0) >= MAX_PER_DAY:
        return 0
    kept = 0
    for e in events[:MAX_EVENTS]:
        if e.get("kind") not in KINDS:
            continue
        duration = e.get("duration_ms")
        session.add(
            BetaEvent(
                beta_number=user.beta_number,
                kind=e["kind"],
                path=clean_path(str(e.get("path") or "")),
                duration_ms=int(duration) if isinstance(duration, int | float) else None,
                detail=str(e["detail"])[:200] if e.get("detail") else None,
            )
        )
        kept += 1
    await session.commit()
    return kept


def _won(bet: Bet) -> bool:
    """Gagné : le pari rapporte plus que la mise (un pari réglé en partie peut perdre)."""
    return (bet.payout or 0) > bet.stake


async def observatory(session: AsyncSession, now: datetime | None = None) -> dict[str, Any]:
    """Activité des testeurs volontaires, sans nom ni numéro de téléphone."""
    now = now or datetime.now(UTC)
    testers = list(
        await session.scalars(
            select(User).where(User.beta_sharing.is_(True), User.beta_number.is_not(None))
        )
    )
    numbers = {u.id: int(u.beta_number or 0) for u in testers}
    ids = list(numbers)
    bets = list(
        await session.scalars(select(Bet).where(Bet.user_id.in_(ids), Bet.status == "settled"))
    ) if ids else []  # fmt: skip
    montantes = list(
        await session.scalars(select(Montante).where(Montante.user_id.in_(ids)))
    ) if ids else []  # fmt: skip
    events = list(
        await session.scalars(
            select(BetaEvent)
            .where(BetaEvent.beta_number.in_(list(numbers.values())))
            .order_by(BetaEvent.created_at.desc())
        )
    ) if ids else []  # fmt: skip

    rows = []
    for uid, number in sorted(numbers.items(), key=lambda x: x[1]):
        mine = [b for b in bets if b.user_id == uid]
        stake = sum(b.stake for b in mine)
        payout = sum(b.payout or 0 for b in mine)
        mont = [m for m in montantes if m.user_id == uid]
        problem = next(
            (e for e in events if e.beta_number == number and e.kind in ("error", "slow")), None
        )
        rows.append({
            "tester": number,
            "bets": len(mine),
            "win_rate": round(sum(_won(b) for b in mine) / len(mine), 4) if mine else None,
            "return": round((payout - stake) / stake, 4) if stake else None,
            "montantes": len(mont),
            "montante_best_step": max((m.current_step for m in mont), default=None),
            "last_problem": None if problem is None else {
                "screen": screen_of(problem.path), "kind": problem.kind,
                "duration_ms": problem.duration_ms, "at": problem.created_at,
            },
        })  # fmt: skip

    recent = [e for e in events if e.created_at >= now - WINDOW]
    by_screen: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"n": 0, "ms": 0, "slow": 0, "errors": 0}
    )
    for e in recent:
        if e.kind == "action":
            continue
        s = by_screen[screen_of(e.path)]
        if e.duration_ms is not None:
            s["n"] += 1
            s["ms"] += e.duration_ms
            s["slow"] += e.duration_ms >= SLOW_MS
        s["errors"] += e.kind == "error"
    screens = sorted(
        (
            {"screen": k, "requests": v["n"],
             "average_ms": round(v["ms"] / v["n"]) if v["n"] else None,
             "over_20s": v["slow"], "errors": v["errors"]}
            for k, v in by_screen.items()
        ),
        key=lambda x: (-(x["over_20s"] + x["errors"]), -(x["average_ms"] or 0)),
    )  # fmt: skip

    markets: dict[str, list[float]] = defaultdict(lambda: [0, 0.0, 0, 0])  # n, Σp, n_p, gagnés
    if bets:
        sels = await session.scalars(
            select(BetSelection).where(BetSelection.bet_id.in_([b.id for b in bets]))
        )
        for sel in sels:
            if sel.result not in ("win", "half_win", "loss", "half_loss"):
                continue
            m = markets[family_of(f"{sel.market}|{sel.line}|{sel.selection}")]
            m[0] += 1
            if sel.model_probability is not None:
                m[1] += float(sel.model_probability)
                m[2] += 1
            m[3] += sel.result in ("win", "half_win")
    market_rows = sorted(
        (
            {"market": k, "selections": int(v[0]),
             "announced": round(v[1] / v[2], 4) if v[2] else None,
             "observed": round(v[3] / v[0], 4)}
            for k, v in markets.items()
        ),
        key=lambda x: -int(x["selections"] or 0),
    )  # fmt: skip

    actions: defaultdict[str, int] = defaultdict(int)
    for e in events:
        if e.kind == "action":
            actions[e.path] += 1
    lost_steps = [m.current_step for m in montantes if m.status == "lost"]
    total_stake = sum(b.stake for b in bets)
    return {
        "testers": rows,
        "summary": {
            "testers": len(rows),
            "bets": len(bets),
            "return": round((sum(b.payout or 0 for b in bets) - total_stake) / total_stake, 4)
            if total_stake
            else None,
            "over_20s_7_days": sum(s["over_20s"] for s in screens),
            "errors_7_days": sum(s["errors"] for s in screens),
        },
        "screens": screens,
        "markets": market_rows,
        "smart_coupons": {
            "composed": actions.get("coupon_compose", 0),
            "added": actions.get("coupon_add", 0),
        },
        "montantes_lost_at_step": dict(
            sorted({s: lost_steps.count(s) for s in set(lost_steps)}.items())
        ),
    }


async def export(session: AsyncSession) -> dict[str, Any]:
    """Export sans données personnelles : l'Observatoire et chaque événement (numéro de
    testeur, date, nature, écran, durée)."""
    data = await observatory(session)
    events = await session.scalars(select(BetaEvent).order_by(BetaEvent.id))
    data["events"] = [
        {"tester": e.beta_number, "at": e.created_at, "kind": e.kind, "screen": screen_of(e.path),
         "path": e.path, "duration_ms": e.duration_ms, "detail": e.detail}
        for e in events
    ]  # fmt: skip
    data["exported_at"] = datetime.now(UTC)
    return data


async def erase(session: AsyncSession) -> dict[str, int]:
    """Fin de la période de test : événements supprimés, numéros de testeur retirés."""
    removed = await session.scalar(select(func.count()).select_from(BetaEvent)) or 0
    testers = (
        await session.scalar(
            select(func.count()).select_from(User).where(User.beta_number.is_not(None))
        )
        or 0
    )
    await session.execute(delete(BetaEvent))
    await session.execute(
        update(User)
        .where(User.beta_number.is_not(None))
        .values(beta_sharing=False, beta_number=None)
    )
    await session.commit()
    return {"events": int(removed), "testers": int(testers)}
