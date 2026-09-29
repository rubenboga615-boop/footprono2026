"""Ligne de commande d'ingestion.

Exemples :
    footprono-ingest all                                  # téléchargement, saison 2016 → en cours
    footprono-ingest football-data --seasons 2024-2025 --competitions EPL,LIGUE_1
    footprono-ingest football-data --from-dir ~/data/football-data
    footprono-ingest understat --from-dir ~/data/understat --seasons 2025
    footprono-ingest quality

Code de sortie : 0 si tout est bon (avertissements compris), 1 si un fichier a
échoué ou si les contrôles de qualité relèvent une erreur, 2 pour un argument
invalide.
"""

import argparse
import asyncio
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from footprono.core.config import Settings, get_settings
from footprono.db.session import create_engine, create_session_factory
from footprono.football.models import DataSource
from footprono.ingestion.quality import current_season_start, run_quality_checks
from footprono.ingestion.reference import COMPETITIONS, COMPETITIONS_BY_CODE
from footprono.ingestion.service import IngestionRequest, run_ingestion

FIRST_SEASON = 2016


def parse_seasons(value: str) -> list[int]:
    """``2024`` → [2024] ; ``2016-2025`` → [2016, …, 2025] ; ``2019,2021`` → [2019, 2021]."""
    years: set[int] = set()
    for part in value.split(","):
        part = part.strip()
        first, sep, last = part.partition("-")
        try:
            start, end = int(first), int(last) if sep else int(first)
        except ValueError:
            raise argparse.ArgumentTypeError(f"saison invalide : {part!r}") from None
        if start > end or not (1990 <= start <= 2100 and 1990 <= end <= 2100):
            raise argparse.ArgumentTypeError(f"plage de saisons invalide : {part!r}")
        years.update(range(start, end + 1))
    return sorted(years)


def parse_competitions(value: str) -> list[str]:
    codes = [c.strip().upper() for c in value.split(",") if c.strip()]
    unknown = [c for c in codes if c not in COMPETITIONS_BY_CODE]
    if unknown or not codes:
        raise argparse.ArgumentTypeError(
            f"compétition inconnue : {', '.join(unknown) or value!r} "
            f"(valeurs : {', '.join(COMPETITIONS_BY_CODE)})"
        )
    return codes


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="footprono-ingest", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("football-data", "résultats, statistiques et cotes (football-data.co.uk)"),
        ("understat", "xG et statistiques avancées (understat.com)"),
        ("all", "football-data puis Understat"),
    ):
        cmd = sub.add_parser(name, help=help_text)
        cmd.add_argument(
            "--seasons",
            type=parse_seasons,
            help=f"années de début de saison (défaut : {FIRST_SEASON} → saison en cours)",
        )
        cmd.add_argument(
            "--competitions",
            type=parse_competitions,
            default=[c.code for c in COMPETITIONS],
            help="codes séparés par des virgules (défaut : toutes)",
        )
        if name == "all":
            cmd.add_argument("--football-data-dir", type=Path, help="import local football-data")
            cmd.add_argument("--understat-dir", type=Path, help="import local Understat")
        else:
            cmd.add_argument(
                "--from-dir", type=Path, help="importer un dossier local au lieu de télécharger"
            )
    sub.add_parser("quality", help="contrôles de qualité sur les données en base")
    parser.add_argument("--json", action="store_true", help="afficher le rapport complet en JSON")
    return parser


def build_requests(args: argparse.Namespace) -> list[IngestionRequest]:
    seasons = args.seasons or list(range(FIRST_SEASON, current_season_start() + 1))
    if args.command == "football-data":
        return [
            IngestionRequest(DataSource.FOOTBALL_DATA, args.competitions, seasons, args.from_dir)
        ]
    if args.command == "understat":
        return [IngestionRequest(DataSource.UNDERSTAT, args.competitions, seasons, args.from_dir)]
    return [
        IngestionRequest(
            DataSource.FOOTBALL_DATA, args.competitions, seasons, args.football_data_dir
        ),
        IngestionRequest(DataSource.UNDERSTAT, args.competitions, seasons, args.understat_dir),
    ]


def print_summary(report: dict[str, Any]) -> None:
    if "run_id" in report:
        print(f"Ingestion n°{report['run_id']} : {report['status']}")
    for f in report.get("files", []):
        line = f"  [{f['status']:<11}] {f['source']:<13} {f['competition']:<10} {f['season']}"
        if f["status"] == "ok":
            line += (
                f"  matchs +{f['matches_inserted']} ~{f['matches_updated']}"
                f"  cotes {f['odds_upserted']}  stats {f['advanced_stats_upserted']}"
                f"  anomalies {len(f['issues'])}"
            )
        else:
            line += f"  {f['error']}"
        print(line)
    quality = report.get("quality", report)
    print(
        f"Qualité : {quality['status']} — {quality['errors']} erreur(s), "
        f"{quality['warnings']} avertissement(s)"
    )
    for finding in quality["findings"]:
        print(
            f"  {finding['severity']:<7} {finding['competition']:<10} {finding['season']} "
            f"{finding['check']} : {finding['message']}"
        )


def _print_progress(message: str) -> None:
    # Sur stderr : la progression reste visible même avec --json sur stdout.
    print(message, file=sys.stderr, flush=True)


async def run(args: argparse.Namespace, settings: Settings) -> int:
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        if args.command == "quality":
            async with factory() as session:
                report = await run_quality_checks(session)
            failed = report["errors"] > 0
        else:
            report = await run_ingestion(
                factory, settings, build_requests(args), progress=_print_progress
            )
            failed = report["status"] != "ok"
    finally:
        await engine.dispose()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print_summary(report)
    return 1 if failed else 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    # Le rapport sort sur stdout ; les journaux (relances, erreurs) sur stderr.
    logging.basicConfig(
        level=logging.WARNING, stream=sys.stderr, format="%(levelname)s %(name)s %(message)s"
    )
    return asyncio.run(run(args, settings))


if __name__ == "__main__":
    sys.exit(main())
