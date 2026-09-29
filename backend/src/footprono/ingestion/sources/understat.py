"""Source Understat : xG et statistiques avancées par match.

Endpoint : https://understat.com/getLeagueData/<ligue>/<année de début de saison>
(JSON). Understat a déjà renommé ses clés : la liste des matchs et le
dictionnaire des équipes sont détectés par leur forme, pas par leur nom.

Deux entrées produisent les mêmes enregistrements :
- ``parse_league_json`` : réponse brute de l'endpoint ;
- ``parse_export_dir`` : export CSV (``matches.csv`` + ``team_matches.csv``)
  produit par le script de téléchargement Understat du projet.
"""

import csv
import io
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from footprono.ingestion.sources.common import ParseIssues, to_decimal, to_int

BASE_URL = "https://understat.com/getLeagueData"


def league_url(slug: str, start_year: int) -> str:
    return f"{BASE_URL}/{slug}/{start_year}"


@dataclass(frozen=True)
class UnderstatMatch:
    source_id: str | None
    kickoff: datetime
    is_result: bool
    home_team: str
    away_team: str
    home_goals: int | None
    away_goals: int | None


@dataclass(frozen=True)
class UnderstatTeamMatch:
    """Statistiques d'une équipe dans un match, vues depuis cette équipe."""

    team: str
    kickoff: datetime
    side: str  # « h » ou « a »
    xg: Decimal | None
    xga: Decimal | None
    npxg: Decimal | None
    npxga: Decimal | None
    ppda_att: int | None
    ppda_def: int | None
    ppda_allowed_att: int | None
    ppda_allowed_def: int | None
    deep: int | None
    deep_allowed: int | None
    xpts: Decimal | None


@dataclass
class UnderstatSeason:
    matches: list[UnderstatMatch]
    team_matches: list[UnderstatTeamMatch]
    issues: ParseIssues


def _parse_datetime(value: Any) -> datetime:
    return datetime.strptime(str(value).strip(), "%Y-%m-%d %H:%M:%S")


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"


def _team_name(node: Any) -> str:
    if isinstance(node, dict):
        return str(node.get("title") or node.get("short_title") or "")
    return str(node or "")


def _find_matches(data: dict[str, Any]) -> list[dict[str, Any]] | None:
    for value in data.values():
        if (
            isinstance(value, list)
            and value
            and isinstance(value[0], dict)
            and "h" in value[0]
            and "a" in value[0]
        ):
            return value
    return None


def _find_teams(data: dict[str, Any]) -> dict[str, Any] | None:
    for value in data.values():
        if isinstance(value, dict) and value:
            first = next(iter(value.values()))
            if isinstance(first, dict) and "history" in first:
                return value
    return None


def _team_match(team: str, h: dict[str, Any]) -> UnderstatTeamMatch:
    ppda = h.get("ppda") or {}
    ppda_allowed = h.get("ppda_allowed") or {}
    return UnderstatTeamMatch(
        team=team,
        kickoff=_parse_datetime(h["date"]),
        side=str(h["h_a"]),
        xg=to_decimal(h.get("xG")),
        xga=to_decimal(h.get("xGA")),
        npxg=to_decimal(h.get("npxG")),
        npxga=to_decimal(h.get("npxGA")),
        ppda_att=to_int(_str(ppda.get("att"))),
        ppda_def=to_int(_str(ppda.get("def"))),
        ppda_allowed_att=to_int(_str(ppda_allowed.get("att"))),
        ppda_allowed_def=to_int(_str(ppda_allowed.get("def"))),
        deep=to_int(_str(h.get("deep"))),
        deep_allowed=to_int(_str(h.get("deep_allowed"))),
        xpts=to_decimal(h.get("xpts")),
    )


def _str(value: Any) -> str | None:
    return None if value is None else str(value)


def parse_league_json(data: Any) -> UnderstatSeason:
    issues = ParseIssues()
    if not isinstance(data, dict):
        raise ValueError("réponse Understat inattendue : objet JSON attendu")
    raw_matches = _find_matches(data)
    raw_teams = _find_teams(data)
    if raw_matches is None:
        raise ValueError("réponse Understat sans liste de matchs reconnaissable")
    if raw_teams is None:
        raise ValueError("réponse Understat sans statistiques d'équipes reconnaissables")

    matches = []
    for m in raw_matches:
        try:
            goals = m.get("goals") or {}
            matches.append(
                UnderstatMatch(
                    source_id=_str(m.get("id")),
                    kickoff=_parse_datetime(m.get("datetime") or m.get("date")),
                    is_result=_to_bool(m.get("isResult")),
                    home_team=_team_name(m.get("h")),
                    away_team=_team_name(m.get("a")),
                    home_goals=to_int(_str(goals.get("h"))),
                    away_goals=to_int(_str(goals.get("a"))),
                )
            )
        except (KeyError, ValueError, TypeError) as exc:
            issues.add(f"match Understat {m.get('id')} ignoré : {exc}")

    team_matches = []
    for team in raw_teams.values():
        title = str(team.get("title") or "")
        for h in team.get("history", []):
            try:
                team_matches.append(_team_match(title, h))
            except (KeyError, ValueError, TypeError) as exc:
                issues.add(f"ligne d'historique {title} ignorée : {exc}")
    return UnderstatSeason(matches, team_matches, issues)


def parse_export_dir(matches_csv: bytes, team_matches_csv: bytes) -> UnderstatSeason:
    issues = ParseIssues()
    matches = []
    for row in csv.DictReader(io.StringIO(matches_csv.decode("utf-8"))):
        try:
            matches.append(
                UnderstatMatch(
                    source_id=row.get("match_id") or None,
                    kickoff=_parse_datetime(row["date"]),
                    is_result=_to_bool(row["is_result"]),
                    home_team=row["home_team"],
                    away_team=row["away_team"],
                    home_goals=to_int(row.get("home_goals")),
                    away_goals=to_int(row.get("away_goals")),
                )
            )
        except (KeyError, ValueError) as exc:
            issues.add(f"match Understat {row.get('match_id')} ignoré : {exc}")

    team_matches = []
    for row in csv.DictReader(io.StringIO(team_matches_csv.decode("utf-8"))):
        try:
            team_matches.append(
                _team_match(
                    row["team"],
                    {
                        **row,
                        "ppda": {"att": row.get("ppda_att"), "def": row.get("ppda_def")},
                        "ppda_allowed": {
                            "att": row.get("ppda_allowed_att"),
                            "def": row.get("ppda_allowed_def"),
                        },
                    },
                )
            )
        except (KeyError, ValueError) as exc:
            issues.add(f"ligne d'historique {row.get('team')} ignorée : {exc}")
    return UnderstatSeason(matches, team_matches, issues)
