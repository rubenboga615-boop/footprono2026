"""Source football-data.co.uk : résultats, statistiques et cotes (CSV par saison et division).

URL : https://www.football-data.co.uk/mmz4281/<saison>/<division>.csv
Convention de football-data (notes.txt, à confirmer : non consultable depuis
l'environnement de développement) : cotes sans « C » = pré-match, publiées avant
le match ; cotes avec « C » = clôture (coup d'envoi). Une cote de clôture ne doit
jamais servir de variable explicative pour une prédiction publiée avant le match.
"""

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal

from footprono.football.models import OddsTiming
from footprono.ingestion.sources.common import OddsQuote, ParseIssues, to_decimal, to_int

# Sans « www » : l'adresse avec « www » redirige (constaté par l'ancien téléchargeur).
BASE_URL = "https://football-data.co.uk/mmz4281"

# Bookmakers conservés en base. Le fichier brut, archivé tel quel, garde tous
# les autres : ils peuvent être réintégrés sans nouveau téléchargement.
#   B365 : Bet365 · PS : Pinnacle (référence « sharp ») · BFE : Betfair Exchange
#   Max / Avg : meilleure cote et moyenne du marché (2019-20 et après)
#   BbMx / BbAv : meilleure cote et moyenne BetBrain (jusqu'en 2018-19)
KEPT_BOOKMAKERS = ("B365", "PS", "BFE", "Max", "Avg", "BbMx", "BbAv")

# Tous les préfixes de bookmakers connus de football-data, pour reconnaître
# les colonnes sans ambiguïté (le préfixe « P » désigne aussi Pinnacle).
_ALL_BOOKMAKERS = (
    "1XB", "B365", "BbAv", "BbMx", "BF", "BFD", "BFE", "BMGM", "BS", "BV", "BW",
    "CL", "GB", "IW", "LB", "Max", "Avg", "P", "PP", "PS", "SB", "SJ", "SKB", "SO", "VC", "WH",
)  # fmt: skip
_BOOKMAKER_ALIASES = {"P": "PS"}

_BK = "|".join(sorted((re.escape(b) for b in _ALL_BOOKMAKERS), key=len, reverse=True))
_RE_1X2 = re.compile(rf"^(?P<bk>{_BK})(?P<close>C?)(?P<sel>[HDA])$")
_RE_OU25 = re.compile(rf"^(?P<bk>{_BK})(?P<close>C?)(?P<sel>[<>])2\.5$")

_SELECTIONS_1X2 = {"H": "home", "D": "draw", "A": "away"}
_SELECTIONS_OU = {">": "over", "<": "under"}

_STAT_COLUMNS = {
    "home_shots": "HS", "away_shots": "AS",
    "home_shots_on_target": "HST", "away_shots_on_target": "AST",
    "home_corners": "HC", "away_corners": "AC",
    "home_fouls": "HF", "away_fouls": "AF",
    "home_yellow_cards": "HY", "away_yellow_cards": "AY",
    "home_red_cards": "HR", "away_red_cards": "AR",
}  # fmt: skip


def file_url(season_code: str, division: str) -> str:
    return f"{BASE_URL}/{season_code}/{division}.csv"


@dataclass
class FootballDataMatch:
    match_date: date
    kickoff_time: time | None
    home_team: str
    away_team: str
    home_goals: int | None
    away_goals: int | None
    home_goals_ht: int | None
    away_goals_ht: int | None
    stats: dict[str, int | None]
    referee: str | None
    odds: list[OddsQuote] = field(default_factory=list)

    @property
    def finished(self) -> bool:
        return self.home_goals is not None and self.away_goals is not None


def classify_odds_column(column: str) -> tuple[str, str, Decimal, OddsTiming, str] | None:
    """Colonne de cote → (bookmaker, marché, ligne, moment, sélection), ou None."""
    for regex, market, line, selections in (
        (_RE_1X2, "1X2", Decimal(0), _SELECTIONS_1X2),
        (_RE_OU25, "OU", Decimal("2.5"), _SELECTIONS_OU),
    ):
        m = regex.match(column)
        if m:
            bookmaker = _BOOKMAKER_ALIASES.get(m["bk"], m["bk"])
            timing = OddsTiming.CLOSE if m["close"] else OddsTiming.PRE
            return bookmaker, market, line, timing, selections[m["sel"]]
    return None


def _decode(content: bytes) -> str:
    # Les fichiers récents sont en UTF-8 (parfois avec BOM), les anciens en Latin-1.
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("latin-1")


def _parse_date(value: str) -> date:
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError(f"date illisible : {value!r}")


def _parse_time(value: str | None) -> time | None:
    if not value or not value.strip():
        return None
    return datetime.strptime(value.strip(), "%H:%M").time()


def parse_csv(
    content: bytes, *, kept_bookmakers: tuple[str, ...] = KEPT_BOOKMAKERS
) -> tuple[list[FootballDataMatch], ParseIssues]:
    issues = ParseIssues()
    reader = csv.DictReader(io.StringIO(_decode(content)))
    fieldnames = [f for f in (reader.fieldnames or []) if f]
    odds_columns = {
        col: spec
        for col in fieldnames
        if (spec := classify_odds_column(col)) and spec[0] in kept_bookmakers
    }

    matches: list[FootballDataMatch] = []
    for line_no, row in enumerate(reader, start=2):
        home, away = (row.get("HomeTeam") or "").strip(), (row.get("AwayTeam") or "").strip()
        if not home and not away:
            continue  # lignes vides en fin de fichier
        try:
            match = FootballDataMatch(
                match_date=_parse_date(row["Date"]),
                kickoff_time=_parse_time(row.get("Time")),
                home_team=home,
                away_team=away,
                home_goals=to_int(row.get("FTHG")),
                away_goals=to_int(row.get("FTAG")),
                home_goals_ht=to_int(row.get("HTHG")),
                away_goals_ht=to_int(row.get("HTAG")),
                stats={name: to_int(row.get(col)) for name, col in _STAT_COLUMNS.items()},
                referee=(row.get("Referee") or "").strip() or None,
            )
        except (KeyError, ValueError) as exc:
            issues.add(f"ligne {line_no} ignorée : {exc}")
            continue

        for col, (bookmaker, market, line, timing, selection) in odds_columns.items():
            price = to_decimal(row.get(col))
            if price is None:
                continue
            if price <= 1:
                issues.add(f"ligne {line_no} : cote {col}={price} invalide (≤ 1) ignorée")
                continue
            match.odds.append(OddsQuote(bookmaker, market, line, timing, selection, price))
        matches.append(match)
    return matches, issues
