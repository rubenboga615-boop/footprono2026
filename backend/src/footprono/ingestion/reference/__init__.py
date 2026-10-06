"""Référentiel : compétitions couvertes et correspondance des noms d'équipes."""

import csv
from dataclasses import dataclass
from datetime import date
from functools import cache
from importlib import resources

from footprono.football.models import DataSource


@dataclass(frozen=True)
class CompetitionRef:
    code: str
    name: str
    country: str
    n_teams: int
    # Division football-data ; None : API-Football est la source des résultats et des
    # tirs (championnats que football-data ne détaille pas).
    football_data_division: str | None
    # Understat (xG) ne couvre que les 5 grands championnats : None ailleurs
    # (niveau de données 2, engine/tiers.py).
    understat_slug: str | None
    api_football_id: int
    # Nombres d'équipes admis selon les saisons (contrôle de qualité).
    team_counts: tuple[int, ...] = (18, 20)
    # Seconde phase après la saison régulière (Belgique, Grèce, Écosse) : la même affiche
    # revient (Match.leg), plus de matchs qu'un simple aller-retour, calendrier non
    # équilibré ; ces contrôles ne s'appliquent pas.
    playoffs: bool = False
    # Saison sur l'année civile (Norvège, Suède : mars à novembre) : la saison 2026 est
    # celle de 2026, et non celle qui commence en juillet.
    calendar_year: bool = False


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
    # Seconde phase : après 33 journées, chaque équipe joue cinq matchs de plus dans son
    # groupe de six (haut ou bas du tableau).
    CompetitionRef(
        "SCO", "Premiership", "Scotland", 12, "SC0", None, 179, team_counts=(12,), playoffs=True
    ),
    # Résultats et tirs d'API-Football (historique depuis 2018) : docs/MOTEUR.md,
    # « Suisse, Norvège, Suède… avec les tirs d'API-Football ».
    CompetitionRef(
        "SUI",
        "Super League",
        "Switzerland",
        12,
        None,
        None,
        207,
        team_counts=(10, 12),
        playoffs=True,
    ),
    CompetitionRef(
        "NOR", "Eliteserien", "Norway", 16, None, None, 103, team_counts=(16,), calendar_year=True
    ),
    CompetitionRef(
        "SWE", "Allsvenskan", "Sweden", 16, None, None, 113, team_counts=(16,), calendar_year=True
    ),
    CompetitionRef(
        "DEN", "Superliga", "Denmark", 12, None, None, 119, team_counts=(12, 14), playoffs=True
    ),
    CompetitionRef(
        "AUT", "Bundesliga", "Austria", 12, None, None, 218, team_counts=(12,), playoffs=True
    ),
    # Même source (archive api-football-historique, depuis 2018) : docs/MOTEUR.md,
    # « Pologne, Tchéquie, Croatie, Roumanie en service ». Seconde phase ou tours
    # supplémentaires partout (Croatie : quatre rencontres par affiche). Australie
    # écartée : moins bonne que la référence naïve, favoris surestimés.
    CompetitionRef(
        "POL", "Ekstraklasa", "Poland", 18, None, None, 106, team_counts=(16, 18), playoffs=True
    ),
    CompetitionRef(
        "CZE",
        "First League",
        "Czech-Republic",
        16,
        None,
        None,
        345,
        team_counts=(16, 18),
        playoffs=True,
    ),
    CompetitionRef("CRO", "HNL", "Croatia", 10, None, None, 210, team_counts=(10,), playoffs=True),
    CompetitionRef(
        "ROU", "Liga I", "Romania", 16, None, None, 283, team_counts=(14, 16), playoffs=True
    ),
)
COMPETITIONS_BY_CODE = {c.code: c for c in COMPETITIONS}


def current_season(competition: "CompetitionRef | str", today: date | None = None) -> int:
    """Saison en cours d'un championnat : année civile (Norvège, Suède) ou année de
    début d'une saison qui reprend en juillet-août."""
    ref = COMPETITIONS_BY_CODE[competition] if isinstance(competition, str) else competition
    today = today or date.today()
    if ref.calendar_year:
        return today.year
    return today.year if today.month >= 7 else today.year - 1


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
    (
        "SCO",
        2019,
    ): "championnat arrêté en mars 2020 (COVID-19) après 30 journées, sans seconde phase",
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
