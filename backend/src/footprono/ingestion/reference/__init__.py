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
    # Étude du 06/11/2026 (docs/MOTEUR.md, « Serbie et Israël en service ; Chypre
    # écartée ») : 14 équipes en Serbie depuis 2026-27.
    CompetitionRef(
        "SRB", "Super Liga", "Serbia", 16, None, None, 286, team_counts=(14, 16, 20), playoffs=True
    ),
    CompetitionRef(
        "ISR", "Ligat ha'Al", "Israel", 14, None, None, 383, team_counts=(14,), playoffs=True
    ),
)
COMPETITIONS_BY_CODE = {c.code: c for c in COMPETITIONS}


@dataclass(frozen=True)
class CupRef:
    """Coupe d'Europe : moteur à part (Elo commun aux championnats et aux coupes,
    résultats seulement), jamais mêlée aux modèles des championnats."""

    code: str
    name: str
    api_football_id: int
    first_season: int


CUPS: tuple[CupRef, ...] = (
    CupRef("UCL", "Ligue des Champions", 2, 2018),
    CupRef("UEL", "Ligue Europa", 3, 2018),
    CupRef("UECL", "Ligue Conférence", 848, 2021),
)
CUPS_BY_CODE = {c.code: c for c in CUPS}
# Dossiers de l'archive de l'historique API-Football (collecte de la console).
CUP_ARCHIVE_DIRS = {"UCL": "UCL", "UEL": "UEL", "UECL": "UECL"}
LEAGUE_CODES: tuple[str, ...] = tuple(c.code for c in COMPETITIONS)


@dataclass(frozen=True)
class NationRef:
    """Compétition de sélections nationales : moteur à part (résultats seulement), jamais
    mêlée aux modèles des championnats ni des coupes. ``official`` : faux pour les amicaux
    (servent aux notes, pas de pronostic publié)."""

    code: str
    name: str
    api_football_id: int
    official: bool = True


# Codes = dossiers de l'archive de l'historique (ingestion/history.py, NATIONAL).
NATIONS: tuple[NationRef, ...] = (
    NationRef("CAN", "Coupe d'Afrique des Nations", 6),
    NationRef("CANQ", "CAN : éliminatoires", 36),
    NationRef("WC", "Coupe du Monde", 1),
    NationRef("WCQ_AFR", "Coupe du Monde : éliminatoires Afrique", 29),
    NationRef("WCQ_EUR", "Coupe du Monde : éliminatoires Europe", 32),
    NationRef("WCQ_SAM", "Coupe du Monde : éliminatoires Amérique du Sud", 34),
    NationRef("EURO", "Euro", 4),
    NationRef("EUROQ", "Euro : éliminatoires", 960),
    NationRef("UNL", "Ligue des Nations", 5),
    NationRef("COPA", "Copa America", 9),
    NationRef("AMICAL", "Matchs amicaux", 10, official=False),
)
NATIONS_BY_CODE = {n.code: n for n in NATIONS}
# Ni championnat ni coupe d'Europe : hors des modèles et contrôles des championnats.
NON_LEAGUE_CODES: tuple[str, ...] = (*CUPS_BY_CODE, *NATIONS_BY_CODE)


@dataclass(frozen=True)
class FinalPhase:
    """Phase finale d'un tournoi : dates, pays hôtes (noms API-Football) et, pour un
    tournoi à plusieurs pays, les villes de chacun. Terrain neutre sauf pour un pays hôte
    qui reçoit chez lui."""

    start: date
    end: date
    hosts: dict[str, frozenset[str] | None]  # None : toutes les villes du tournoi


def _cities(*names: str) -> frozenset[str]:
    return frozenset(names)


# Dates : la CAN 2019 d'API-Football mêle éliminatoires et phase finale (même saison,
# « Group Stage ») ; seules les dates les séparent.
FINAL_PHASES: dict[tuple[str, int], FinalPhase] = {
    ("CAN", 2019): FinalPhase(date(2019, 6, 21), date(2019, 7, 19), {"Egypt": None}),
    ("CAN", 2021): FinalPhase(date(2022, 1, 9), date(2022, 2, 6), {"Cameroon": None}),
    ("CAN", 2023): FinalPhase(date(2024, 1, 13), date(2024, 2, 11), {"Ivory Coast": None}),
    ("CAN", 2025): FinalPhase(date(2025, 12, 21), date(2026, 1, 18), {"Morocco": None}),
    ("WC", 2018): FinalPhase(date(2018, 6, 14), date(2018, 7, 15), {"Russia": None}),
    ("WC", 2022): FinalPhase(date(2022, 11, 20), date(2022, 12, 18), {"Qatar": None}),
    ("WC", 2026): FinalPhase(date(2026, 6, 11), date(2026, 7, 19), {
        "Mexico": _cities("Mexico City", "Zapopan", "Monterrey"),
        "Canada": _cities("Toronto", "Vancouver"),
        "USA": _cities(
            "Inglewood", "Santa Clara", "East Rutherford", "Boston", "Houston", "Arlington",
            "Philadelphia", "Atlanta", "Seattle", "Miami Gardens", "Kansas City", "Dallas",
            "New-York", "San-Francisco", "Miami", "Los Angeles",
        ),
    }),
    ("EURO", 2020): FinalPhase(date(2021, 6, 11), date(2021, 7, 11), {
        "Italy": _cities("Roma"), "Azerbaijan": _cities("Baku"),
        "Denmark": _cities("København"), "Russia": _cities("St. Petersburg"),
        "England": _cities("London"), "Romania": _cities("Bucureşti"),
        "Netherlands": _cities("Amsterdam"), "Scotland": _cities("Glasgow"),
        "Spain": _cities("Sevilla"), "Hungary": _cities("Budapest"),
        "Germany": _cities("München"),
    }),
    ("EURO", 2024): FinalPhase(date(2024, 6, 14), date(2024, 7, 14), {"Germany": None}),
    ("COPA", 2019): FinalPhase(date(2019, 6, 14), date(2019, 7, 7), {"Brazil": None}),
    ("COPA", 2021): FinalPhase(date(2021, 6, 13), date(2021, 7, 11), {"Brazil": None}),
    ("COPA", 2024): FinalPhase(date(2024, 6, 20), date(2024, 7, 15), {}),  # États-Unis
}  # fmt: skip


def nation_neutral(code: str, season: int, day: date, home: str, city: str | None) -> bool:
    """Terrain neutre d'un match de sélections : en phase finale, sauf pays hôte chez lui
    (le club qui reçoit est celui listé à domicile) ; ailleurs, l'équipe qui reçoit joue
    chez elle (éliminatoires, Ligue des Nations, amicaux)."""
    phase = FINAL_PHASES.get((code, season))
    if phase is None or not phase.start <= day <= phase.end:
        return False
    if home not in phase.hosts:
        return True
    cities = phase.hosts[home]
    return cities is not None and city not in cities


def cup_season(today: date | None = None) -> int:
    """Saison d'une coupe d'Europe : année de début (les qualifications commencent en juin)."""
    today = today or date.today()
    return today.year if today.month >= 6 else today.year - 1


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
