"""Référentiel : compétitions couvertes et correspondance des noms d'équipes."""

import csv
from dataclasses import dataclass
from functools import cache
from importlib import resources

from footprono.football.models import DataSource


@dataclass(frozen=True)
class CompetitionRef:
    code: str
    name: str
    country: str
    n_teams: int
    football_data_division: str
    understat_slug: str
    api_football_id: int


COMPETITIONS: tuple[CompetitionRef, ...] = (
    CompetitionRef("EPL", "Premier League", "England", 20, "E0", "EPL", 39),
    CompetitionRef("LA_LIGA", "La Liga", "Spain", 20, "SP1", "La_liga", 140),
    CompetitionRef("SERIE_A", "Serie A", "Italy", 20, "I1", "Serie_A", 135),
    CompetitionRef("BUNDESLIGA", "Bundesliga", "Germany", 18, "D1", "Bundesliga", 78),
    CompetitionRef("LIGUE_1", "Ligue 1", "France", 18, "F1", "Ligue_1", 61),
)
COMPETITIONS_BY_CODE = {c.code: c for c in COMPETITIONS}


@dataclass(frozen=True)
class TeamRef:
    competition: str
    name: str
    aliases: dict[DataSource, str]


@cache
def load_teams() -> tuple[TeamRef, ...]:
    """Référentiel des équipes (``teams.csv``) : nom canonique et alias par source."""
    text = resources.files(__package__).joinpath("teams.csv").read_text(encoding="utf-8")
    teams = []
    for row in csv.DictReader(text.splitlines()):
        aliases = {
            DataSource(source): row[source]
            for source in ("football_data", "understat")
            if row.get(source)
        }
        teams.append(TeamRef(row["competition"], row["name"], aliases))
    return tuple(teams)


def season_code(start_year: int) -> str:
    """Code de saison football-data : 2025 → « 2526 »."""
    return f"{start_year % 100:02d}{(start_year + 1) % 100:02d}"


# Saisons arrêtées avant leur terme : les matchs non joués y sont « annulés »
# (jamais « à venir ») et le contrôle de complétude en tient compte.
_COVID_LIGUE_1 = "championnat arrêté en mars 2020 (COVID-19), classement figé après 28 journées"
INTERRUPTED_SEASONS: dict[tuple[str, int], str] = {("LIGUE_1", 2019): _COVID_LIGUE_1}
