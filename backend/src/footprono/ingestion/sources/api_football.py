"""Source API-Football : statistiques de match par équipe et par période.

Deux entrées produisent les mêmes enregistrements :
- ``parse_collector_file`` : fichier ``<ligue>/<saison>.json`` du collecteur
  (``collect-stats.mjs`` de l'ancien projet) — libellés indexés une fois
  (``types``) et valeurs en tableaux alignés, périodes ``ft``/``h1``/``h2`` ;
- ``ApiFootballClient`` : téléchargement direct (``/fixtures`` puis
  ``/fixtures/statistics?half=true``), avec respect des deux quotas du service
  (par jour et par minute).

Conventions d'API-Football, vérifiées sur 5 ligues-saisons contre football-data :
- un compteur absent (tirs, corners, cartons…) vaut 0 : les cartons rouges
  « vides » correspondent à 0 dans football-data dans 99,9 % des cas ;
- une mesure absente (possession, passes, xG) est inconnue et reste ``None`` ;
- les fautes et « goals_prevented » ne sont jamais fournis par mi-temps.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from footprono.football.models import StatPeriod
from footprono.ingestion.raw_store import USER_AGENT, SourceUnavailableError
from footprono.ingestion.sources.common import ParseIssues

logger = logging.getLogger(__name__)

BASE_URL = "https://v3.football.api-sports.io"

# Libellé API-Football → colonne de ``match_team_stats``.
STAT_COLUMNS: dict[str, str] = {
    "Shots on Goal": "shots_on_goal",
    "Shots off Goal": "shots_off_goal",
    "Total Shots": "total_shots",
    "Blocked Shots": "blocked_shots",
    "Shots insidebox": "shots_inside_box",
    "Shots outsidebox": "shots_outside_box",
    "Fouls": "fouls",
    "Corner Kicks": "corners",
    "Offsides": "offsides",
    "Ball Possession": "possession",
    "Yellow Cards": "yellow_cards",
    "Red Cards": "red_cards",
    "Goalkeeper Saves": "goalkeeper_saves",
    "Total passes": "total_passes",
    "Passes accurate": "passes_accurate",
    "Passes %": "passes_pct",
    "expected_goals": "expected_goals",
    "goals_prevented": "goals_prevented",
}
# Compteurs : absents = 0 (convention d'API-Football).
COUNT_COLUMNS = frozenset(
    {
        "shots_on_goal",
        "shots_off_goal",
        "total_shots",
        "blocked_shots",
        "shots_inside_box",
        "shots_outside_box",
        "fouls",
        "corners",
        "offsides",
        "yellow_cards",
        "red_cards",
        "goalkeeper_saves",
    }
)
DECIMAL_COLUMNS = frozenset({"possession", "passes_pct", "expected_goals", "goals_prevented"})
# Jamais fournis par mi-temps : ``None``, pas 0.
NOT_PER_HALF = frozenset({"fouls", "goals_prevented"})
# Le découpage par mi-temps (paramètre ``half``) n'existe qu'à partir de cette saison.
HALF_SPLIT_FIRST_SEASON = 2024

# Requêtes restantes dans la minute en dessous desquelles on attend (limite : 300/min).
MINUTE_WINDOW_GUARD = 30

FINISHED_STATUSES = frozenset({"FT", "AET", "PEN"})

TeamStats = dict[str, int | Decimal | None]


@dataclass
class ApiFixture:
    fixture_id: int
    match_date: date
    home_team: str
    away_team: str
    home_goals: int | None
    away_goals: int | None
    home_goals_ht: int | None
    away_goals_ht: int | None
    referee: str | None = None
    # Période → (statistiques domicile, statistiques extérieur). Vide si le
    # service n'a pas de statistiques pour ce match.
    stats: dict[StatPeriod, tuple[TeamStats, TeamStats]] = field(default_factory=dict)


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value).strip().rstrip("%"))
    except InvalidOperation:
        return None


def normalize(raw: dict[str, Any], period: StatPeriod, issues: ParseIssues) -> TeamStats:
    """Libellés API → colonnes, conversion des valeurs et règle des absents."""
    out: TeamStats = {}
    for label, value in raw.items():
        column = STAT_COLUMNS.get(label)
        if column is None:
            issues.add(f"statistique API-Football inconnue ignorée : {label!r}")
            continue
        if column in DECIMAL_COLUMNS:
            out[column] = _to_decimal(value)
        elif value is None:
            out[column] = None
        else:
            number = _to_decimal(value)
            out[column] = int(number) if number is not None else None
    for column in STAT_COLUMNS.values():
        out.setdefault(column, None)
        if column in NOT_PER_HALF and period is not StatPeriod.FULL:
            out[column] = None
        elif column in COUNT_COLUMNS and out[column] is None:
            out[column] = 0
    return out


# --- Fichiers du collecteur ----------------------------------------------------

_COLLECTOR_PERIODS = (
    ("ft", StatPeriod.FULL),
    ("h1", StatPeriod.FIRST_HALF),
    ("h2", StatPeriod.SECOND_HALF),
)


def parse_collector_file(data: Any) -> tuple[list[ApiFixture], ParseIssues]:
    issues = ParseIssues()
    if not isinstance(data, dict) or not isinstance(data.get("fixtures"), list):
        raise ValueError("fichier du collecteur API-Football inattendu : clé « fixtures » absente")
    types: list[str] | None = data.get("types")
    fixtures = []
    for f in data["fixtures"]:
        fixture = ApiFixture(
            fixture_id=int(f["id"]),
            match_date=date.fromisoformat(f["d"]),
            home_team=f["h"],
            away_team=f["a"],
            home_goals=f.get("hg"),
            away_goals=f.get("ag"),
            home_goals_ht=f.get("ht"),
            away_goals_ht=f.get("at"),
        )
        for key, period in _COLLECTOR_PERIODS:
            sides = f.get(key)
            if types and isinstance(sides, list) and len(sides) == 2:
                home, away = (
                    normalize(dict(zip(types, values, strict=True)), period, issues)
                    for values in sides
                )
                fixture.stats[period] = (home, away)
        fixtures.append(fixture)
    return fixtures, issues


# --- Réponses brutes de l'API --------------------------------------------------


def normalize_referee(value: Any) -> str | None:
    """« Anthony Taylor, England » → « Anthony Taylor » ; vide → None."""
    name = str(value or "").split(",")[0].strip()
    return name or None


def parse_fixture(item: dict[str, Any]) -> ApiFixture:
    """Un élément de ``/fixtures`` (sans statistiques)."""
    halftime = item.get("score", {}).get("halftime") or {}
    return ApiFixture(
        referee=normalize_referee(item["fixture"].get("referee")),
        fixture_id=int(item["fixture"]["id"]),
        match_date=date.fromisoformat(item["fixture"]["date"][:10]),
        home_team=item["teams"]["home"]["name"],
        away_team=item["teams"]["away"]["name"],
        home_goals=item["goals"]["home"],
        away_goals=item["goals"]["away"],
        home_goals_ht=halftime.get("home"),
        away_goals_ht=halftime.get("away"),
    )


def is_finished_league_match(item: dict[str, Any]) -> bool:
    """Match terminé de la saison régulière (les barrages sont exclus)."""
    finished = item["fixture"]["status"]["short"] in FINISHED_STATUSES
    return finished and str(item.get("league", {}).get("round", "")).startswith("Regular Season")


def parse_statistics(
    response: list[dict[str, Any]], home_team_id: int, issues: ParseIssues
) -> dict[StatPeriod, tuple[TeamStats, TeamStats]]:
    """Réponse de ``/fixtures/statistics`` → statistiques par période."""
    if len(response) < 2 or not isinstance(response[0].get("statistics"), list):
        return {}
    blocks = sorted(response[:2], key=lambda b: b["team"]["id"] != home_team_id)
    out: dict[StatPeriod, tuple[TeamStats, TeamStats]] = {}
    for key, period in (
        ("statistics", StatPeriod.FULL),
        ("statistics_1h", StatPeriod.FIRST_HALF),
        ("statistics_2h", StatPeriod.SECOND_HALF),
    ):
        if all(isinstance(b.get(key), list) for b in blocks):
            home, away = (
                normalize({s["type"]: s["value"] for s in b[key]}, period, issues) for b in blocks
            )
            out[period] = (home, away)
    return out


class ApiFootballError(SourceUnavailableError):
    pass


class ApiFootballClient:
    """Client respectueux des quotas : par jour (budget + réserve) et par minute.

    ``min_remaining`` laisse une réserve de requêtes quotidiennes à d'autres
    usages (archivage des cotes en direct, dont une cote manquée est perdue).
    """

    def __init__(
        self,
        key: str,
        *,
        budget: int,
        min_remaining: int,
        pause_seconds: float = 0.4,
        base_url: str = BASE_URL,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"x-apisports-key": key, "User-Agent": USER_AGENT},
            timeout=60.0,
            transport=transport,
        )
        self.budget = budget
        self.min_remaining = min_remaining
        self.pause_seconds = pause_seconds
        self.used = 0
        self.day_remaining: int | None = None
        self._key_validated = False

    async def __aenter__(self) -> "ApiFootballClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self._client.aclose()

    def can_spend(self) -> bool:
        if self.used >= self.budget:
            return False
        return self.day_remaining is None or self.day_remaining > self.min_remaining

    async def status(self) -> dict[str, Any]:
        """Vérifie la clé et lit le quota du jour (``/status`` ne consomme pas de quota)."""
        body = await self._get("/status", {}, count=False)
        requests = body["response"]["requests"]
        self.day_remaining = int(requests["limit_day"]) - int(requests["current"])
        self._key_validated = True
        return dict(body["response"])

    async def get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.can_spend():
            raise ApiFootballError("budget API-Football atteint pour cette exécution")
        return await self._get(path, params, count=True)

    async def _get(self, path: str, params: dict[str, Any], *, count: bool) -> dict[str, Any]:
        for attempt in (1, 2):
            if count:
                self.used += 1
            try:
                response = await self._client.get(path, params=params)
            except httpx.HTTPError as exc:
                if attempt == 2:
                    raise ApiFootballError(f"API-Football {path} : {type(exc).__name__}") from exc
                await asyncio.sleep(2)
                continue
            minute_window_full = self._read_quota(response)
            if response.status_code in (401, 403):
                body = response.text[:300]
                # Après validation de la clé, un 403 vient du limiteur (Cloudflare) :
                # attendre la fenêtre d'une minute, une fois.
                if self._key_validated and attempt == 1:
                    logger.warning("api_football_rate_limited", extra={"path": path})
                    await asyncio.sleep(65)
                    continue
                raise ApiFootballError(
                    f"API-Football refuse la clé (HTTP {response.status_code}) : {body}",
                    transient=self._key_validated,
                )
            if response.status_code == 429 or response.status_code >= 500:
                if attempt == 2:
                    raise ApiFootballError(f"API-Football {path} : HTTP {response.status_code}")
                await asyncio.sleep(5)
                continue
            body_json: dict[str, Any] = response.json()
            errors = body_json.get("errors")
            if errors:
                raise ApiFootballError(f"API-Football {path} : {errors}", transient=False)
            # Fenêtre d'une minute presque pleine : attendre sa réinitialisation
            # plutôt que de la franchir.
            await asyncio.sleep(65 if minute_window_full else self.pause_seconds)
            return body_json
        raise ApiFootballError(f"API-Football {path} : échec")

    def _read_quota(self, response: httpx.Response) -> bool:
        """Met à jour le quota du jour ; indique si la fenêtre d'une minute est presque pleine."""
        day = response.headers.get("x-ratelimit-requests-remaining")
        if day is not None:
            self.day_remaining = int(day)
        minute = response.headers.get("x-ratelimit-remaining")
        return minute is not None and int(minute) <= MINUTE_WINDOW_GUARD
