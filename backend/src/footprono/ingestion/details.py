"""Détails d'un match tirés de ``/fixtures?ids=`` : événements, relevé en direct,
compositions, statistiques des joueurs (plan du 10/11/2026, étape 1).

La même réponse sert au suivi en direct (toutes les 2 minutes, ``live.follow_live``), à la
relecture des relevés déjà gardés sur le disque et au rattrapage des matchs passés. Chaque
bloc est remplacé en entier : la dernière réponse fait foi (un but annulé par la VAR
disparaît, une composition corrigée remplace l'ancienne).
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.football.models import (
    LiveSnapshot,
    MatchEvent,
    MatchLineup,
    MatchLineupPlayer,
    PlayerMatchStats,
)

# Statuts où le match se joue (mi-temps comprise) ou vient de finir.
PLAYING = frozenset({"1H", "HT", "2H", "ET", "BT", "P", "LIVE", "SUSP", "INT"})
FINISHED = frozenset({"FT", "AET", "PEN"})


@dataclass
class Stored:
    events: int = 0
    snapshots: int = 0
    lineups: int = 0
    players: int = 0
    stat_types: set[str] = field(default_factory=set)

    def add(self, other: "Stored") -> None:
        self.events += other.events
        self.snapshots += other.snapshots
        self.lineups += other.lineups
        self.players += other.players
        self.stat_types |= other.stat_types

    def summary(self) -> str:
        return (
            f"{self.events} événements, {self.snapshots} relevés, {self.lineups} compositions, "
            f"{self.players} fiches de joueurs"
        )


def _int(value: Any) -> int | None:
    try:
        return int(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None


def _dec(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value)) if value not in (None, "") else None
    except InvalidOperation:
        return None


def _text(value: Any, size: int) -> str | None:
    return str(value)[:size] if value not in (None, "") else None


def _side(team: Any, home_id: int | None) -> str | None:
    team_id = _int((team or {}).get("id"))
    if team_id is None or home_id is None:
        return None
    return "home" if team_id == home_id else "away"


def team_stats(item: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Statistiques des deux équipes, ``{type: valeur}`` telles que données (toutes)."""
    home_id = _int(item.get("teams", {}).get("home", {}).get("id"))
    out: dict[str, dict[str, Any]] = {}
    for block in item.get("statistics") or []:
        side = _side(block.get("team"), home_id)
        if side and isinstance(block.get("statistics"), list):
            out[side] = {str(s.get("type")): s.get("value") for s in block["statistics"]}
    return out.get("home"), out.get("away")


async def store(
    session: AsyncSession,
    match_id: int,
    item: dict[str, Any],
    taken_at: datetime,
    raw_file_id: int | None = None,
) -> Stored:
    """Range les blocs présents dans un élément de ``/fixtures?ids=``."""
    done = Stored()
    home_id = _int(item.get("teams", {}).get("home", {}).get("id"))
    status = str(item.get("fixture", {}).get("status", {}).get("short") or "")

    events = item.get("events")
    if isinstance(events, list) and (events or status in PLAYING | FINISHED):
        await session.execute(delete(MatchEvent).where(MatchEvent.match_id == match_id))
        rows = [
            {
                "match_id": match_id,
                "seq": i,
                "minute": _int(e.get("time", {}).get("elapsed")),
                "extra": _int(e.get("time", {}).get("extra")),
                "side": _side(e.get("team"), home_id),
                "kind": _text(e.get("type"), 16) or "?",
                "detail": _text(e.get("detail"), 64),
                "player_api_id": _int((e.get("player") or {}).get("id")),
                "player": _text((e.get("player") or {}).get("name"), 96),
                "assist_api_id": _int((e.get("assist") or {}).get("id")),
                "assist": _text((e.get("assist") or {}).get("name"), 96),
                "comments": _text(e.get("comments"), 160),
            }
            for i, e in enumerate(events)
            if isinstance(e, dict)
        ]
        if rows:
            await session.execute(insert(MatchEvent).values(rows))
        done.events = len(rows)

    if status in PLAYING | FINISHED:
        home_stats, away_stats = team_stats(item)
        done.stat_types = set(home_stats or {}) | set(away_stats or {})
        elapsed = item.get("fixture", {}).get("status", {})
        goals = item.get("goals") or {}
        values = {
            "match_id": match_id,
            "taken_at": taken_at,
            "status": status[:8],
            "minute": _int(elapsed.get("elapsed")) or 0,
            "extra": _int(elapsed.get("extra")) or 0,
            "home_goals": _int(goals.get("home")),
            "away_goals": _int(goals.get("away")),
            "home_stats": home_stats,
            "away_stats": away_stats,
            "raw_file_id": raw_file_id,
        }
        stmt = insert(LiveSnapshot).values(values)
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=["match_id", "status", "minute", "extra"],
                set_={
                    k: stmt.excluded[k]
                    for k in (
                        "taken_at",
                        "home_goals",
                        "away_goals",
                        "home_stats",
                        "away_stats",
                        "raw_file_id",
                    )
                },
                # Relevés relus dans le désordre : le plus récent l'emporte.
                where=LiveSnapshot.taken_at <= stmt.excluded.taken_at,
            )
        )
        done.snapshots = 1

    lineups = item.get("lineups")
    if isinstance(lineups, list) and lineups:
        await session.execute(delete(MatchLineup).where(MatchLineup.match_id == match_id))
        await session.execute(
            delete(MatchLineupPlayer).where(MatchLineupPlayer.match_id == match_id)
        )
        teams: list[dict[str, Any]] = []
        players: list[dict[str, Any]] = []
        for block in lineups:
            side = _side(block.get("team"), home_id)
            if side is None or any(t["side"] == side for t in teams):
                continue
            coach = block.get("coach") or {}
            teams.append(
                {
                    "match_id": match_id,
                    "side": side,
                    "formation": _text(block.get("formation"), 16),
                    "coach_api_id": _int(coach.get("id")),
                    "coach": _text(coach.get("name"), 96),
                }
            )
            for key, starter in (("startXI", True), ("substitutes", False)):
                for entry in block.get(key) or []:
                    p = (entry or {}).get("player") or {}
                    if not p.get("name"):
                        continue
                    players.append(
                        {
                            "match_id": match_id,
                            "side": side,
                            "starter": starter,
                            "player_api_id": _int(p.get("id")),
                            "name": _text(p.get("name"), 96),
                            "number": _int(p.get("number")),
                            "position": _text(p.get("pos"), 4),
                            "grid": _text(p.get("grid"), 8),
                        }
                    )
        if teams:
            await session.execute(insert(MatchLineup).values(teams))
        if players:
            await session.execute(insert(MatchLineupPlayer).values(players))
        done.lineups = len(teams)

    blocks = item.get("players")
    if isinstance(blocks, list) and blocks:
        by_player: dict[int, dict[str, Any]] = {}
        for block in blocks:
            side = _side(block.get("team"), home_id)
            for entry in block.get("players") or []:
                p = (entry or {}).get("player") or {}
                pid = _int(p.get("id"))
                stats = ((entry or {}).get("statistics") or [{}])[0] or {}
                if side is None or pid is None or not p.get("name"):
                    continue
                games, goals = stats.get("games") or {}, stats.get("goals") or {}
                shots, cards = stats.get("shots") or {}, stats.get("cards") or {}
                by_player[pid] = {
                    "match_id": match_id,
                    "side": side,
                    "player_api_id": pid,
                    "name": _text(p.get("name"), 96),
                    "minutes": _int(games.get("minutes")),
                    "rating": _dec(games.get("rating")),
                    "goals": _int(goals.get("total")),
                    "assists": _int(goals.get("assists")),
                    "shots": _int(shots.get("total")),
                    "shots_on": _int(shots.get("on")),
                    "yellow": _int(cards.get("yellow")),
                    "red": _int(cards.get("red")),
                    "stats": stats,
                }
        if by_player:
            await session.execute(
                delete(PlayerMatchStats).where(PlayerMatchStats.match_id == match_id)
            )
            await session.execute(insert(PlayerMatchStats).values(list(by_player.values())))
        done.players = len(by_player)
    return done
