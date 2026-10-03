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
    # Understat (xG) ne couvre que les 5 grands championnats : None ailleurs
    # (niveau de données 2, engine/tiers.py).
    understat_slug: str | None
    api_football_id: int
    # Nombres d'équipes admis selon les saisons (contrôle de qualité).
    team_counts: tuple[int, ...] = (18, 20)
    # Phase finale après la saison régulière (Belgique) : plus de matchs qu'un simple
    # aller-retour, calendrier non équilibré ; ces contrôles ne s'appliquent pas.
    playoffs: bool = False


COMPETITIONS: tuple[CompetitionRef, ...] = (
    CompetitionRef("EPL", "Premier League", "England", 20, "E0", "EPL", 39),
    CompetitionRef("LA_LIGA", "La Liga", "Spain", 20, "SP1", "La_liga", 140),
    CompetitionRef("SERIE_A", "Serie A", "Italy", 20, "I1", "Serie_A", 135),
    CompetitionRef("BUNDESLIGA", "Bundesliga", "Germany", 18, "D1", "Bundesliga", 78),
    CompetitionRef("LIGUE_1", "Ligue 1", "France", 18, "F1", "Ligue_1", 61),
    # Niveau 2 (tirs, sans xG) : docs/MOTEUR.md, « Étude Portugal et Belgique ».
    CompetitionRef("POR", "Liga Portugal", "Portugal", 18, "P1", None, 94, team_counts=(16, 18)),
    CompetitionRef(
        "BEL", "Pro League", "Belgium", 16, "B1", None, 144, team_counts=(16, 18), playoffs=True
    ),
    # docs/MOTEUR.md, « Championnats candidats ».
    CompetitionRef("NED", "Eredivisie", "Netherlands", 18, "N1", None, 88, team_counts=(18,)),
    CompetitionRef(
        "GRE", "Super League", "Greece", 14, "G1", None, 197, team_counts=(14, 16), playoffs=True
    ),
    CompetitionRef("TUR", "Süper Lig", "Turkey", 18, "T1", None, 203, team_counts=(18, 19, 20, 21)),
)
COMPETITIONS_BY_CODE = {c.code: c for c in COMPETITIONS}


@dataclass(frozen=True)
class TeamRef:
    competition: str
    name: str
    # Une source peut avoir changé l'orthographe d'une équipe au fil des saisons
    # (API-Football : « Bayern München » puis « Bayern Munich ») : plusieurs alias.
    aliases: dict[DataSource, tuple[str, ...]]


@cache
def load_teams() -> tuple[TeamRef, ...]:
    """Référentiel des équipes (``teams.csv``) : nom canonique et alias par source."""
    text = resources.files(__package__).joinpath("teams.csv").read_text(encoding="utf-8")
    teams = []
    for row in csv.DictReader(text.splitlines()):
        aliases = {
            DataSource(source): tuple(row[source].split("|"))
            for source in ("football_data", "understat", "api_football")
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
INTERRUPTED_SEASONS: dict[tuple[str, int], str] = {
    ("LIGUE_1", 2019): _COVID_LIGUE_1,
    (
        "BEL",
        2019,
    ): "championnat arrêté en mars 2020 (COVID-19) après 29 journées, sans phase finale",
    ("GRE", 2018): "derby Panathinaïkos - Olympiakos du 17 mars 2019 jamais joué",
    ("NED", 2019): "championnat arrêté en mars 2020 (COVID-19) après 26 journées, sans classement",
}


_TUR_2022_HATAY_HOME = (
    "Konyaspor", "Sivasspor", "Fatih Karagümrük", "MKE Ankaragücü", "İstanbulspor",
    "Fenerbahçe", "Ümraniyespor", "Galatasaray",
)  # fmt: skip
_TUR_2022_HATAY_AWAY = (
    "Adana Demirspor", "Kayserispor", "Alanyaspor", "Beşiktaş", "Başakşehir",
    "Giresunspor", "Antalyaspor",
)  # fmt: skip
_TUR_2022_GAZIANTEP_HOME = (
    "Galatasaray", "Trabzonspor", "Kasımpaşa", "Konyaspor", "Alanyaspor",  # noqa: RUF001
    "Fatih Karagümrük", "Giresunspor", "İstanbulspor",
)  # fmt: skip
_TUR_2022_GAZIANTEP_AWAY = (
    "Ümraniyespor", "Adana Demirspor", "Kayserispor", "Beşiktaş", "Başakşehir", "Fenerbahçe",
)  # fmt: skip

# Matchs perdus sur tapis vert : le score officiel n'est pas le score joué, et
# les sources ne suivent pas la même convention. Exclus de l'apprentissage.
# (compétition, saison, domicile, extérieur) avec les noms du référentiel.
AWARDED_MATCHES: frozenset[tuple[str, int, str, str]] = frozenset(
    {
        ("SERIE_A", 2016, "Sassuolo", "Pescara"),
        ("SERIE_A", 2020, "Verona", "Roma"),
        ("BUNDESLIGA", 2024, "Union Berlin", "Bochum"),
        ("LIGUE_1", 2016, "SC Bastia", "Lyon"),
    }
    # Turquie 2022-23 : Hatayspor et Gaziantep retirés après le séisme du 6 février
    # 2023, leurs matchs restants donnés perdus 0-3 sans être joués.
    | {("TUR", 2022, "Hatayspor", away) for away in _TUR_2022_HATAY_HOME}
    | {("TUR", 2022, home, "Hatayspor") for home in _TUR_2022_HATAY_AWAY}
    | {("TUR", 2022, "Gaziantep FK", away) for away in _TUR_2022_GAZIANTEP_HOME}
    | {("TUR", 2022, home, "Gaziantep FK") for home in _TUR_2022_GAZIANTEP_AWAY}
)
