"""Onglet « En direct » de l'écran d'un match (plan du 10/11/2026, étape 7 ; maquettes D2 à
D4) : chronologie, statistiques (match, 1re et 2e mi-temps), compositions.

Tout vient de ce que le suivi en direct a rangé (étape 1). Statistiques d'une mi-temps : le
relevé pris à la pause donne la 1re ; la 2e est la différence avec le dernier relevé (sauf
les pourcentages, qui ne se soustraient pas). Sans relevé à la pause (match complété après
coup), seules les statistiques du match sont données.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.football.models import (
    LiveSnapshot,
    MatchEvent,
    MatchLineup,
    MatchLineupPlayer,
)


def _number(value: Any) -> float | None:
    """Valeur comptable d'une statistique (« 1.21 » → 1,21) ; None pour un pourcentage ou un
    texte."""
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    text = str(value).strip()
    if text.endswith("%"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def second_half(full: dict[str, Any] | None, first: dict[str, Any] | None) -> dict[str, Any] | None:
    """Statistiques de la 2e mi-temps : match moins 1re mi-temps, pour ce qui se compte."""
    if not full or first is None:
        return None
    out: dict[str, Any] = {}
    for key, value in full.items():
        a, b = _number(value), _number(first.get(key))
        if a is None or b is None:
            continue
        diff = max(a - b, 0.0)
        out[key] = round(diff, 2) if isinstance(value, str) else round(diff)
    return out


async def live_view(session: AsyncSession, match_id: int) -> dict[str, Any]:
    events = [
        {
            "minute": e.minute,
            "extra": e.extra,
            "side": e.side,
            "kind": e.kind,
            "detail": e.detail,
            "player": e.player,
            "player_id": e.player_api_id,
            "assist_id": e.assist_api_id,
            "assist": e.assist,
            "comments": e.comments,
        }
        for e in await session.scalars(
            select(MatchEvent).where(MatchEvent.match_id == match_id).order_by(MatchEvent.seq)
        )
    ]
    snaps = list(
        await session.scalars(
            select(LiveSnapshot)
            .where(LiveSnapshot.match_id == match_id)
            .order_by(LiveSnapshot.taken_at.desc())
        )
    )
    latest = snaps[0] if snaps else None
    pause = next((s for s in snaps if s.status == "HT"), None)
    stats: dict[str, Any] | None = None
    if latest is not None and (latest.home_stats or latest.away_stats):
        first = (
            {"home": pause.home_stats or {}, "away": pause.away_stats or {}}
            if pause is not None and latest is not pause and (pause.home_stats or pause.away_stats)
            else None
        )
        stats = {
            "match": {"home": latest.home_stats or {}, "away": latest.away_stats or {}},
            "first": first,
            "second": None
            if first is None
            else {
                "home": second_half(latest.home_stats, first["home"]),
                "away": second_half(latest.away_stats, first["away"]),
            },
            "updated_at": latest.taken_at.isoformat(),
        }

    teams = {
        t.side: t
        for t in await session.scalars(select(MatchLineup).where(MatchLineup.match_id == match_id))
    }
    players = list(
        await session.scalars(
            select(MatchLineupPlayer)
            .where(MatchLineupPlayer.match_id == match_id)
            .order_by(MatchLineupPlayer.id)
        )
    )
    lineups = [
        {
            "side": side,
            "formation": t.formation,
            "coach": t.coach,
            "players": [
                {
                    "name": p.name,
                    "id": p.player_api_id,
                    "number": p.number,
                    "position": p.position,
                    "grid": p.grid,
                    "starter": p.starter,
                }
                for p in players
                if p.side == side
            ],
        }
        for side in ("home", "away")
        if (t := teams.get(side)) is not None
    ]
    return {
        "status": latest.status if latest else None,
        "minute": latest.minute if latest else None,
        "extra": latest.extra if latest else None,
        "events": events,
        "stats": stats,
        "lineups": lineups,
    }
