"""Collecte de l'historique d'API-Football (matchs, journées, statistiques de match).

Pour étudier de nouvelles compétitions avant de les ajouter, puis les importer
(action « Importer l'historique API-Football ») : championnats, coupes d'Europe
des clubs, compétitions de sélections nationales. Lancée depuis la console
d'administration (auparavant ``scripts/termux/api-football-history.sh``, même
dossier, même rangement : une collecte commencée par le script reprend ici).

Rangement : ``<dossier>/<code>/league.json``, ``<code>/<année>/fixtures.json``
et ``<code>/<année>/statistics.jsonl`` (une ligne par match). Rien n'est
redemandé d'une fois sur l'autre, sauf la liste des matchs des deux dernières
saisons. La collecte s'arrête d'elle-même quand il ne reste plus que
``reserve`` requêtes du jour (laissées au serveur) ; la relancer le lendemain
reprend où elle s'était arrêtée. Aucune donnée personnelle ; la clé n'est
jamais écrite.

Coût : 1 requête par saison pour la liste des matchs, puis 1 par match terminé
pour ses statistiques (environ 250 par saison de championnat). Coupes d'Europe :
statistiques de la phase principale seulement ; sélections nationales :
résultats seulement.

Fonctions synchrones : la console les exécute dans un fil à part.
"""

import json
import os
import tarfile
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import httpx

from footprono.ingestion.quality import current_season_start
from footprono.ingestion.sources.api_football import BASE_URL

# Remplacé dans les tests (aucune requête réelle).
transport: httpx.BaseTransport | None = None
PAUSE_SECONDS = 0.25


@dataclass(frozen=True)
class League:
    """Compétition collectée.

    ``stats`` : "all" tous les matchs terminés, "main" hors tours préliminaires et de
    qualification, "none" aucune (résultats seulement). ``hint`` : mot attendu dans le
    nom chez API-Football (contrôle de l'identifiant).
    """

    api_id: int
    country: str
    label: str
    stats: str
    hint: str = ""


# L'ordre est l'ordre de priorité.
CLUBS = {
    "SWZ": League(207, "Switzerland", "Suisse · Super League", "all"),
    "NOR": League(103, "Norway", "Norvège · Eliteserien", "all"),
    "SWE": League(113, "Sweden", "Suède · Allsvenskan", "all"),
    "DNK": League(119, "Denmark", "Danemark · Superliga", "all"),
    "AUT": League(218, "Austria", "Autriche · Bundesliga", "all"),
    "POL": League(106, "Poland", "Pologne · Ekstraklasa", "all"),
    "ROU": League(283, "Romania", "Roumanie · Liga I", "all"),
    "AUS": League(188, "Australia", "Australie · A-League", "all"),
    "CZE": League(345, "Czech-Republic", "Tchéquie · 1re division", "all"),
    "CRO": League(210, "Croatia", "Croatie · HNL", "all"),
    "SRB": League(286, "Serbia", "Serbie · Super Liga", "all"),
    "ISR": League(383, "Israel", "Israël · Ligat ha'Al", "all"),
    "CYP": League(318, "Cyprus", "Chypre · 1re division", "all"),
}
CUPS = {
    "UCL": League(2, "World", "Ligue des Champions", "main", "champions league"),
    "UEL": League(3, "World", "Europa League", "main", "europa league"),
    "UECL": League(848, "World", "Conférence League", "main", "conference league"),
}
NATIONAL = {
    "CAN": League(6, "World", "Coupe d'Afrique des Nations", "none", "africa cup of nations"),
    "CANQ": League(36, "World", "CAN · éliminatoires", "none", "qualification"),
    "WC": League(1, "World", "Coupe du Monde", "none", "world cup"),
    "WCQ_AFR": League(29, "World", "Coupe du Monde · éliminatoires Afrique", "none", "africa"),
    "WCQ_EUR": League(32, "World", "Coupe du Monde · éliminatoires Europe", "none", "europe"),
    "WCQ_SAM": League(
        34, "World", "Coupe du Monde · éliminatoires Amérique du Sud", "none", "south america"
    ),
    "EURO": League(4, "World", "Euro", "none", "euro"),
    "EUROQ": League(960, "World", "Euro · éliminatoires", "none", "qualification"),
    "UNL": League(5, "World", "Ligue des Nations", "none", "nations league"),
    "COPA": League(9, "World", "Copa America", "none", "copa america"),
    "AMICAL": League(10, "World", "Matchs amicaux", "none", "friendlies"),
}
LEAGUES = {**CLUBS, **CUPS, **NATIONAL}
GROUPS = {"CLUBS": CLUBS, "COUPES": CUPS, "SELECTIONS": NATIONAL}
PRELIMINARY = ("qualif", "preliminary")
FINISHED = {"FT", "AET", "PEN"}


class QuotaReachedError(Exception):
    pass


class StopRequestedError(Exception):
    pass


def wants_stats(code: str, item: dict[str, Any]) -> bool:
    """Statistiques demandées pour ce match terminé ?"""
    mode = LEAGUES[code].stats
    if mode == "none":
        return False
    rnd = str(item["league"].get("round", "")).lower()
    return mode == "all" or not any(word in rnd for word in PRELIMINARY)


def _load(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _save(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def _done_ids(path: Path) -> set[int]:
    if not path.exists():
        return set()
    with path.open(encoding="utf-8") as f:
        return {json.loads(line)["fixture"] for line in f if line.strip()}


def _finished(fixtures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [f for f in fixtures if f["fixture"]["status"]["short"] in FINISHED]


@dataclass
class _Client:
    http: httpx.Client
    reserve: int
    log: Callable[[str], None]
    should_stop: Callable[[], bool]
    remaining: int | None = None
    used: int = 0

    def get(self, path: str, **params: int | str) -> list[Any]:
        """Une requête ; respecte la limite par minute et la réserve du jour."""
        if self.should_stop():
            raise StopRequestedError
        if self.remaining is not None and self.remaining <= self.reserve:
            raise QuotaReachedError
        for attempt in range(4):
            try:
                r = self.http.get(path, params=params)
            except httpx.HTTPError as e:
                if attempt == 3:
                    raise
                self.log(f"  réseau ({type(e).__name__}), nouvel essai dans 10 s")
                time.sleep(10)
                continue
            self.used += 1
            if "x-ratelimit-requests-remaining" in r.headers:
                self.remaining = int(r.headers["x-ratelimit-requests-remaining"])
            time.sleep(PAUSE_SECONDS)
            body = r.json()
            errors = body.get("errors") or {}
            if errors:
                text = json.dumps(errors, ensure_ascii=False)
                if "requests" in errors:  # quota du jour épuisé
                    raise QuotaReachedError
                if "rateLimit" in errors and attempt < 3:  # limite par minute
                    self.log("  limite par minute atteinte, pause d'une minute")
                    time.sleep(60)
                    continue
                self.log(f"  {path} {params} : erreur {text}")
                return []
            return list(body.get("response") or [])
        return []


@dataclass
class CollectReport:
    used: int = 0
    remaining: int | None = None
    stopped: str | None = None  # "quota", "admin" ou None (terminée)
    missing: int = 0
    skipped: list[str] = field(default_factory=list)
    summary: list[str] = field(default_factory=list)
    archive: Path | None = None


def collect(
    key: str,
    codes: list[str],
    out: Path,
    *,
    first: int = 2018,
    reserve: int = 1500,
    log: Callable[[str], None] = print,
    progress: Callable[[float], None] = lambda _f: None,
    should_stop: Callable[[], bool] = lambda: False,
    archive_to: Path | None = None,
    today: date | None = None,
) -> CollectReport:
    """Télécharge ce qui manque pour ``codes`` (ordre de priorité) ; résumé et archive."""
    today = today or date.today()
    current = current_season_start(today)
    # Saisons sur l'année civile (Norvège, Suède, sélections) : jusqu'à l'année en cours.
    last = max(current, today.year)
    report = CollectReport()
    with httpx.Client(
        base_url=BASE_URL,
        timeout=30,
        headers={"x-apisports-key": key},
        transport=transport,
    ) as http:
        client = _Client(http, reserve, log, should_stop)
        try:
            plan = _list_fixtures(client, codes, out, first, last, current, today, log, report)
            _fetch_statistics(client, plan, out, log, progress)
        except QuotaReachedError:
            report.stopped = "quota"
            log(
                f"\nRéserve du jour atteinte ({reserve} requêtes laissées au serveur) : "
                "arrêt propre."
            )
        except StopRequestedError:
            report.stopped = "admin"
            log("\nArrêt demandé : ce qui est téléchargé est gardé.")
        report.used, report.remaining = client.used, client.remaining

    report.summary, report.missing = summarize(codes, out, first, last, today)
    (out / "RESUME.txt").write_text("\n".join(report.summary) + "\n", encoding="utf-8")
    log("\n".join(report.summary[3:]))
    if archive_to is not None:
        archive = archive_to / f"{out.name}-{today:%Y%m%d}.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(out, arcname=out.name)
        report.archive = archive
        log(f"\nArchive prête ({archive.stat().st_size / 1e6:.1f} Mo) : {archive}")
    log(
        f"Requêtes utilisées : {report.used} · restantes aujourd'hui : "
        f"{report.remaining if report.remaining is not None else '?'}"
    )
    return report


def _list_fixtures(
    client: _Client,
    codes: list[str],
    out: Path,
    first: int,
    last: int,
    current: int,
    today: date,
    log: Callable[[str], None],
    report: CollectReport,
) -> list[tuple[str, int, bool]]:
    """1. Liste des matchs de chaque saison (peu de requêtes) : tout le tableau d'abord."""
    plan: list[tuple[str, int, bool]] = []  # (code, saison, statistiques demandées)
    for code in codes:
        league = LEAGUES[code]
        info_path = out / code / "league.json"
        if info_path.exists() and date.fromtimestamp(info_path.stat().st_mtime) == today:
            info = _load(info_path)
        else:
            info = client.get("/leagues", id=league.api_id)
            _save(info_path, info)
        if not info:
            log(f"\n== {code} · {league.label} : compétition {league.api_id} inconnue, ignorée")
            report.skipped.append(code)
            continue
        got = info[0]["country"]["name"]
        name = info[0]["league"]["name"]
        wrong_country = got.replace("-", " ").lower() != league.country.replace("-", " ").lower()
        if wrong_country or league.hint not in name.lower():
            log(
                f"\n== {code} : l'identifiant {league.api_id} est « {got} · {name} », "
                f"pas « {league.label} » : ignoré (à signaler)"
            )
            report.skipped.append(code)
            continue
        log(f"\n== {code} · {got} · {name}")
        seasons = {s["year"]: s for s in info[0]["seasons"]}
        for year in range(first, last + 1):
            s = seasons.get(year)
            if s is None:
                if year <= current:  # pas d'édition cette année-là (Euro, CAN, Coupe du Monde…)
                    log(f"  {year} : pas de saison chez API-Football")
                continue
            coverage = ((s.get("coverage") or {}).get("fixtures") or {}).get("statistics_fixtures")
            covered = bool(coverage)
            path = out / code / str(year) / "fixtures.json"
            if not path.exists() or year >= current - 1:
                _save(path, client.get("/fixtures", league=league.api_id, season=year))
            fixtures = _load(path)
            if league.stats == "none":
                wanted = "résultats seulement"
            else:
                wanted = f"statistiques {'oui' if covered else 'non'}"
            log(
                f"  {year} : {len(fixtures)} matchs, {len(_finished(fixtures))} terminés · {wanted}"
            )
            plan.append((code, year, covered and league.stats != "none"))
    return plan


def _pending(code: str, folder: Path) -> list[int]:
    fixtures = _load(folder / "fixtures.json")
    done = _done_ids(folder / "statistics.jsonl")
    return [
        f["fixture"]["id"]
        for f in _finished(fixtures)
        if f["fixture"]["id"] not in done and wants_stats(code, f)
    ]


def _fetch_statistics(
    client: _Client,
    plan: list[tuple[str, int, bool]],
    out: Path,
    log: Callable[[str], None],
    progress: Callable[[float], None],
) -> None:
    """2. Statistiques de chaque match terminé (1 requête par match)."""
    todo = {(c, y): _pending(c, out / c / str(y)) for c, y, stats in plan if stats}
    total = sum(len(p) for p in todo.values())
    left = "?" if client.remaining is None else max(0, client.remaining - client.reserve)
    log(f"\nStatistiques à demander : {total} matchs (possibles aujourd'hui : {left})")
    done = 0
    for (code, year), pending in todo.items():
        if not pending:
            continue
        log(f"  {code} {year} : {len(pending)} matchs")
        with (out / code / str(year) / "statistics.jsonl").open("a", encoding="utf-8") as f:
            for n, fixture_id in enumerate(pending, start=1):
                response = client.get("/fixtures/statistics", fixture=fixture_id)
                row = {"fixture": fixture_id, "response": response}
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                f.flush()
                done += 1
                progress(done / total)
                if n % 50 == 0:
                    log(
                        f"    {n}/{len(pending)} — requêtes restantes aujourd'hui "
                        f"{client.remaining}"
                    )


def summarize(
    codes: list[str], out: Path, first: int, last: int, today: date
) -> tuple[list[str], int]:
    """3. Résumé par saison (matchs, terminés, statistiques, journées) ; matchs manquants."""
    lines = [
        f"API-Football, téléchargé le {today:%d/%m/%Y}, saisons {first}-{last}",
        "Par saison : matchs, terminés, avec statistiques (vides), journées.",
        "",
    ]
    missing = 0
    for code in codes:
        folder = out / code
        if not folder.is_dir() or not (folder / "league.json").exists():
            continue
        years = sorted(int(p.name) for p in folder.iterdir() if p.name.isdigit())
        info = _load(folder / "league.json")
        if not years or not info:
            continue
        league = LEAGUES[code]
        covered = {
            s["year"]
            for s in info[0]["seasons"]
            if ((s.get("coverage") or {}).get("fixtures") or {}).get("statistics_fixtures")
            and league.stats != "none"
        }
        lines.append(f"{code} · {league.label}")
        for year in years:
            fixtures = _load(folder / str(year) / "fixtures.json")
            stats: dict[int, list[Any]] = {}
            sp = folder / str(year) / "statistics.jsonl"
            if sp.exists():
                with sp.open(encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            row = json.loads(line)
                            stats[row["fixture"]] = row["response"]
            finished = _finished(fixtures)
            empty = sum(
                1 for f in finished if f["fixture"]["id"] in stats and not stats[f["fixture"]["id"]]
            )
            if year in covered:
                missing += sum(
                    1 for f in finished if f["fixture"]["id"] not in stats and wants_stats(code, f)
                )
                kind = f"{len(stats)} avec statistiques ({empty} vides) · "
            elif league.stats == "none":
                kind = "résultats seulement · "
            else:
                kind = "statistiques non couvertes · "
            rounds = Counter(
                str(f["league"].get("round", "")).rsplit(" - ", 1)[0] for f in fixtures
            )
            lines.append(
                f"  {year} : {len(fixtures)} matchs, {len(finished)} terminés, "
                + kind
                + ", ".join(f"{r} ({n})" for r, n in rounds.most_common(8))
            )
    return lines, missing
