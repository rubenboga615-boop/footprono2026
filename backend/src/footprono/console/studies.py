"""Préparation des études (anciens scripts Termux), exécutée par la console.

- ``api_football_teams`` : noms des équipes d'un championnat chez API-Football,
  saison par saison, et ce qu'API-Football couvre (relier les équipes avant
  d'ajouter un championnat).
- ``football_data_files`` : fichiers de football-data.co.uk (résultats,
  statistiques, cotes) réunis dans une archive pour l'étude.
- ``check_odds`` : contrôle direct des cotes d'un championnat (1 requête).

Fonctions synchrones (la console les exécute dans un fil à part) ; aucune donnée
personnelle, la clé API n'est jamais écrite.
"""

import csv
import io
import json
import tarfile
import time
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx

from footprono.ingestion.quality import current_season_start
from footprono.ingestion.sources.api_football import BASE_URL

Log = Callable[[str], None]
# Remplacé dans les tests (aucune requête réelle).
transport: httpx.BaseTransport | None = None
PAUSE_SECONDS = 0.3

# --- API-Football : équipes et couverture ------------------------------------


def api_football_teams(
    key: str,
    leagues: list[int],
    first: int,
    out: Path,
    log: Log,
    should_stop: Callable[[], bool] = lambda: False,
) -> dict[str, Any]:
    remaining = "?"
    result: dict[str, Any] = {"date": f"{date.today():%Y-%m-%d}", "leagues": {}}
    with httpx.Client(
        base_url=BASE_URL, timeout=30, headers={"x-apisports-key": key}, transport=transport
    ) as client:

        def get(path: str, **params: int) -> dict[str, Any]:
            nonlocal remaining
            r = client.get(path, params=params)
            remaining = r.headers.get("x-ratelimit-requests-remaining", remaining)
            time.sleep(PAUSE_SECONDS)
            body: dict[str, Any] = r.json()
            if body.get("errors"):
                log(f"  {path} {params} : erreurs {body['errors']}")
            return body

        for league in leagues:
            info = get("/leagues", id=league).get("response") or []
            if not info:
                log(f"Championnat {league} inconnu d'API-Football")
                continue
            name = f"{info[0]['country']['name']} · {info[0]['league']['name']}"
            seasons = {s["year"]: s for s in info[0]["seasons"]}
            log(f"\n== {league} · {name}")
            entry: dict[str, Any] = {"name": name, "seasons": {}}
            for year in range(first, current_season_start() + 1):
                if should_stop():
                    break
                s = seasons.get(year)
                if s is None:
                    log(f"  {year} : saison absente d'API-Football")
                    continue
                cov = s.get("coverage") or {}
                fx = cov.get("fixtures") or {}
                teams = [
                    {"id": t["team"]["id"], "name": t["team"]["name"]}
                    for t in get("/teams", league=league, season=year).get("response") or []
                ]
                coverage = {
                    "statistiques": fx.get("statistics_fixtures"),
                    "compositions": fx.get("lineups"),
                    "evenements": fx.get("events"),
                    "cotes": cov.get("odds"),
                    "blessures": cov.get("injuries"),
                }
                entry["seasons"][year] = {
                    "teams": sorted(teams, key=lambda t: t["name"]),
                    "coverage": coverage,
                }
                flags = " · ".join(f"{k} {'oui' if v else 'non'}" for k, v in coverage.items())
                log(f"  {year} : {len(teams)} équipes · {flags}")
            result["leagues"][league] = entry
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"\nRequêtes API-Football restantes aujourd'hui : {remaining}")
    return result


# --- football-data.co.uk -----------------------------------------------------

# Un fichier par saison et par division (statistiques de match pour une partie).
MAIN = {
    "E0": "Angleterre Premier League", "E1": "Angleterre Championship",
    "E2": "Angleterre League One", "E3": "Angleterre League Two",
    "EC": "Angleterre National League",
    "SC0": "Écosse Premiership", "SC1": "Écosse Championship",
    "SC2": "Écosse League One", "SC3": "Écosse League Two",
    "D1": "Allemagne Bundesliga", "D2": "Allemagne 2. Bundesliga",
    "I1": "Italie Serie A", "I2": "Italie Serie B",
    "SP1": "Espagne Liga", "SP2": "Espagne Liga 2",
    "F1": "France Ligue 1", "F2": "France Ligue 2",
    "N1": "Pays-Bas Eredivisie", "B1": "Belgique Pro League", "P1": "Portugal Liga",
    "T1": "Turquie Süper Lig", "G1": "Grèce Super League",
}  # fmt: skip
# Un seul fichier par pays, toutes saisons (résultats et cotes, en général sans statistiques).
EXTRA = {
    "ARG": "Argentine", "AUT": "Autriche", "BRA": "Brésil", "CHN": "Chine",
    "DNK": "Danemark", "FIN": "Finlande", "IRL": "Irlande", "JPN": "Japon",
    "MEX": "Mexique", "NOR": "Norvège", "POL": "Pologne", "ROU": "Roumanie",
    "RUS": "Russie", "SWE": "Suède", "SWZ": "Suisse", "USA": "États-Unis",
}  # fmt: skip


def _describe(raw: bytes) -> str:
    """Matchs, et part des matchs avec tirs, arbitre et cotes Pinnacle."""
    text = raw.decode("utf-8-sig", errors="replace")
    rows = [r for r in csv.DictReader(io.StringIO(text)) if (r.get("HomeTeam") or r.get("Home"))]
    if not rows:
        return "0 match"

    def share(*cols: str) -> str:
        n = sum(1 for r in rows if any((r.get(c) or "").strip() for c in cols))
        return f"{100 * n // len(rows)} %"

    return (
        f"{len(rows)} matchs · tirs {share('HS')} · arbitre {share('Referee')} · "
        f"cotes Pinnacle {share('PSH', 'PH', 'PSCH')}"
    )


def football_data_files(
    divisions: list[str],
    first: int,
    cache: Path,
    archive: Path,
    log: Log,
    progress: Callable[[float], None] = lambda _f: None,
    should_stop: Callable[[], bool] = lambda: False,
) -> int:
    """Télécharge (cache gardé : seule la saison en cours est reprise), puis archive."""
    current = current_season_start()
    seasons = list(range(first, current + 1))

    def code(y: int) -> str:  # 2026 -> « 2627 »
        return f"{y % 100:02d}{(y + 1) % 100:02d}"

    main = [d for d in divisions if d in MAIN]
    extra = [d for d in divisions if d in EXTRA]
    summary = [
        f"football-data.co.uk, téléchargé le {date.today():%d/%m/%Y}, saisons {first}-{current}",
        "Colonnes : nombre de matchs, part avec tirs (HS), arbitre, cotes Pinnacle.",
        "",
    ]
    total = len(main) * len(seasons) + len(extra) or 1
    done = 0
    with httpx.Client(
        timeout=60,
        follow_redirects=True,
        headers={"User-Agent": "FootProba (etude)"},
        transport=transport,
    ) as client:

        def fetch(url: str, path: Path, refresh: bool) -> tuple[str, bytes | None]:
            if path.exists() and not refresh:
                return "déjà là", path.read_bytes()
            for attempt in range(3):
                try:
                    r = client.get(url)
                except httpx.HTTPError as e:
                    if attempt == 2:
                        return f"échec réseau ({type(e).__name__})", None
                    time.sleep(5)
                    continue
                finally:
                    time.sleep(PAUSE_SECONDS)
                if r.status_code == 404:
                    return "absent de la source", None
                if r.status_code != 200 or not r.content.strip():
                    if attempt == 2:
                        return f"échec HTTP {r.status_code}", None
                    continue
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(r.content)
                return "téléchargé", r.content
            return "échec", None

        for div in main:
            log(f"\n== {div} · {MAIN[div]}")
            summary.append(f"{div} · {MAIN[div]}")
            for y in seasons:
                if should_stop():
                    break
                done += 1
                path = cache / "principaux" / div / f"{code(y)}.csv"
                url = f"https://www.football-data.co.uk/mmz4281/{code(y)}/{div}.csv"
                status, raw = fetch(url, path, y == current)
                line = f"  {y}-{(y + 1) % 100:02d} : {status}" + (
                    f" · {_describe(raw)}" if raw else ""
                )
                log(f"[{done}/{total}]{line}")
                summary.append(line)
                progress(done / total)
        for c in extra:
            if should_stop():
                break
            done += 1
            path = cache / "autres" / f"{c}.csv"
            status, raw = fetch(f"https://www.football-data.co.uk/new/{c}.csv", path, True)
            line = f"{c} · {EXTRA[c]} : {status}" + (f" · {_describe(raw)}" if raw else "")
            log(f"[{done}/{total}] {line}")
            summary.append(line)
            progress(done / total)

    (cache / "RESUME.txt").write_text("\n".join(summary) + "\n", encoding="utf-8")
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(cache / "RESUME.txt", arcname="football-data/RESUME.txt")
        for div in main:
            d = cache / "principaux" / div
            if d.is_dir():
                tar.add(d, arcname=f"football-data/principaux/{div}")
        for c in extra:
            p = cache / "autres" / f"{c}.csv"
            if p.exists():
                tar.add(p, arcname=f"football-data/autres/{c}.csv")
    return done


# --- Cotes d'un championnat --------------------------------------------------


def check_odds(key: str, league: int, season: int, log: Log) -> dict[str, Any]:
    """Cotes 1xBet des prochains matchs d'un championnat, telles que les donne API-Football."""
    with httpx.Client(
        base_url=BASE_URL, timeout=30, headers={"x-apisports-key": key}, transport=transport
    ) as client:
        r = client.get("/odds", params={"league": league, "season": season, "bookmaker": 11})
    body: dict[str, Any] = r.json()
    now = datetime.now(UTC)
    log(f"Requête : /odds?league={league}&season={season}&bookmaker=11 (1xBet)")
    log(
        f"Réponse HTTP {r.status_code}, erreurs : {body.get('errors') or 'aucune'}, "
        f"matchs : {body.get('results')}, pages : {body.get('paging')}"
    )
    log(f"Requêtes restantes aujourd'hui : {r.headers.get('x-ratelimit-requests-remaining', '?')}")
    log("")
    shown = 0
    for item in body.get("response") or []:
        if shown == 10:
            break
        shown += 1
        fixture = item["fixture"]
        updated = item.get("update") or "?"
        age = ""
        try:
            delta = now - datetime.fromisoformat(updated)
            age = f" (il y a {delta.days} j {delta.seconds // 3600} h)"
        except ValueError:
            pass
        prices = ""
        for book in item.get("bookmakers", []):
            for bet in book.get("bets", []):
                if bet.get("name") == "Match Winner":
                    prices = " / ".join(f"{v['value']} {v['odd']}" for v in bet["values"])
        log(f"match {fixture['id']} le {str(fixture.get('date', '?'))[:16]}")
        log(f"   mise à jour API-Football : {updated}{age}")
        log(f"   1xBet 1-N-2 : {prices or 'absent'}")
    if not body.get("response"):
        log("Aucune cote renvoyée pour ce championnat et cette saison.")
    return {"status": r.status_code, "results": body.get("results"), "shown": shown}
