"""Actions de la console d'administration.

Pour ajouter une action : écrire sa fonction ``async (ctx, params) -> résumé`` et
l'enregistrer avec ``register(Action(...))``. Elle apparaît dans la console à la
prochaine mise à jour du serveur, avec ses réglages, son risque et son coût.
Les fonctions appelées sont celles des commandes et des tâches planifiées :
la console ne refait pas le travail autrement.
"""

import asyncio
import re
from pathlib import Path
from typing import Any

from footprono.accounts.cli import _push_test
from footprono.bookmaker import smart_coupon
from footprono.console.jobs import JobContext
from footprono.console.registry import Action, Param, register
from footprono.core.errors import AppError
from footprono.football.models import DataSource
from footprono.ingestion import history, live
from footprono.ingestion.coverage import coverage_report, format_coverage
from footprono.ingestion.quality import run_quality_checks
from footprono.ingestion.reference import COMPETITIONS, current_season
from footprono.ingestion.service import IngestionRequest, run_ingestion
from footprono.ingestion.sources import api_football
from footprono.predictions import service as prediction_service
from footprono.predictions.service import DEFAULT_DAYS_AHEAD

_STEP = re.compile(r"^\[(\d+)/(\d+)\]")


def competition_options() -> list[tuple[str, str]]:
    return [(c.code, f"{c.name} ({c.country})") for c in COMPETITIONS]


def _all_codes() -> list[str]:
    return [c.code for c in COMPETITIONS]


SOURCES = [
    (DataSource.FOOTBALL_DATA.value, "football-data (résultats, cotes de clôture)"),
    (DataSource.UNDERSTAT.value, "Understat (xG, 5 grands championnats)"),
    (DataSource.API_FOOTBALL.value, "API-Football (statistiques, autres championnats)"),
]


def _ingestion_logger(ctx: JobContext) -> Any:
    """Progression des ingestions (« [3/40] … ») : journal et barre de progression."""

    def log(message: str) -> None:
        ctx.log(message)
        if m := _STEP.match(message):
            done, total = int(m.group(1)), int(m.group(2))
            if total:
                ctx.progress((done - 1) / total)

    return log


def _ingestion_summary(ctx: JobContext, report: dict[str, Any]) -> str:
    files = report.get("files", [])
    inserted = sum(f.get("matches_inserted", 0) for f in files)
    updated = sum(f.get("matches_updated", 0) for f in files)
    failed = [f for f in files if f["status"] not in ("ok", "incomplete", "skipped")]
    quality = report["quality"]
    for f in failed:
        ctx.log(f"  {f['source']} {f['competition']} {f['season']} : {f.get('error')}")
    for finding in quality["findings"]:
        ctx.log(
            f"  qualité {finding['severity']} {finding['competition']} {finding['season']} "
            f"{finding['check']} : {finding['message']}"
        )
    ctx.result = {
        "run_id": report["run_id"],
        "status": report["status"],
        "files": len(files),
        "failed": len(failed),
        "matches_inserted": inserted,
        "matches_updated": updated,
        "quality_errors": quality["errors"],
        "quality_warnings": quality["warnings"],
    }
    return (
        f"ingestion n°{report['run_id']} {report['status']} : {len(files)} fichiers "
        f"({len(failed)} en échec), +{inserted} matchs, {updated} mis à jour ; qualité "
        f"{quality['errors']} erreur(s), {quality['warnings']} avertissement(s)"
    )


async def ingest_current(ctx: JobContext, params: dict[str, Any]) -> str:
    codes = set(params["competitions"])
    by_season: dict[int, list[str]] = {}
    for c in COMPETITIONS:
        if c.code in codes:
            by_season.setdefault(current_season(c), []).append(c.code)
    requests = [
        IngestionRequest(DataSource(source), season_codes, [season])
        for season, season_codes in sorted(by_season.items())
        for source in params["sources"]
    ]
    report = await run_ingestion(
        ctx.factory, ctx.settings, requests, progress=_ingestion_logger(ctx)
    )
    return _ingestion_summary(ctx, report)


register(
    Action(
        id="ingest_current",
        title="Mettre à jour la saison en cours",
        family="Données",
        description=(
            "Télécharge les résultats, statistiques et cotes de clôture de la saison en cours "
            "(comme chaque matin à 06:15), puis lance les contrôles de qualité."
        ),
        risk="modifie",
        run=ingest_current,
        exclusive=True,
        cost="1 à 3 requêtes API-Football par match terminé non encore relevé",
        duration="5 à 30 min",
        params=(
            Param(
                "competitions",
                "Championnats",
                "choices",
                default=_all_codes(),
                options=competition_options,
            ),
            Param(
                "sources",
                "Sources",
                "choices",
                default=[v for v, _ in SOURCES],
                options=SOURCES,
            ),
        ),
    )
)


async def import_archive(ctx: JobContext, params: dict[str, Any]) -> str:
    folder = await asyncio.to_thread(
        Path(params["folder"] or ctx.settings.history_archive_dir).expanduser
    )
    if not await asyncio.to_thread(folder.is_dir):
        raise AppError(f"dossier introuvable : {folder}")
    ctx.log(f"Dossier : {folder}")
    current = max(current_season(c) for c in COMPETITIONS)
    seasons = list(range(params["first_season"], current + 1))
    request = IngestionRequest(DataSource.API_FOOTBALL, params["competitions"], seasons, folder)
    report = await run_ingestion(
        ctx.factory, ctx.settings, [request], progress=_ingestion_logger(ctx)
    )
    return _ingestion_summary(ctx, report)


register(
    Action(
        id="import_archive",
        title="Importer l'historique API-Football",
        family="Données",
        description=(
            "Charge en base l'historique collecté (résultats, statistiques par match) depuis "
            "le dossier de l'archive. Aucune requête : tout vient des fichiers. Rejouable "
            "sans doublon."
        ),
        risk="modifie",
        run=import_archive,
        exclusive=True,
        cost="aucune requête",
        duration="2 à 20 min",
        params=(
            Param(
                "competitions",
                "Championnats",
                "choices",
                default=_all_codes(),
                options=competition_options,
            ),
            Param("first_season", "Depuis la saison", "int", default=2018, minimum=2010),
            Param(
                "folder",
                "Dossier de l'archive",
                "text",
                default="",
                help="vide : le dossier de collecte du serveur (FP_HISTORY_ARCHIVE_DIR)",
            ),
        ),
    )
)


async def collect_odds(ctx: JobContext, params: dict[str, Any]) -> str:
    async with ctx.factory() as session:
        report = await live.collect_odds(session, ctx.settings, progress=ctx.log)
    if report["status"] == "unavailable":
        raise AppError(f"cotes indisponibles : {report['error']}")
    for issue in report["issues"]:
        ctx.log(f"attention : {issue}")
    ctx.result = {k: report[k] for k in ("status", "matches", "quotes", "changed", "requests")}
    return (
        f"{report['matches']} matchs, {report['quotes']} cotes relevées, {report['changed']} "
        f"nouvelles ou modifiées ({report['requests']} requêtes)"
    )


register(
    Action(
        id="collect_odds",
        title="Relever les cotes",
        family="Données",
        description=(
            "Calendrier et cotes des bookmakers des matchs à venir (comme toutes les 3 heures). "
            "Utile quand un nouveau championnat n'a pas encore de cotes."
        ),
        risk="modifie",
        run=collect_odds,
        cost="20 à 60 requêtes API-Football",
        duration="1 à 5 min",
    )
)


async def predict(ctx: JobContext, params: dict[str, Any]) -> str:
    async with ctx.factory() as session:
        run = await prediction_service.predict_upcoming(
            session, days_ahead=params["days_ahead"], progress=ctx.log
        )
    report = run.report
    for error in report.get("errors", []):
        ctx.log(f"erreur : {error}")
    n = sum(c.get("matches", 0) for c in report.get("competitions", {}).values())
    ctx.result = {"run_id": run.id, "status": run.status, "matches": n}
    return f"exécution n°{run.id} {run.status} : {n} matchs prédits"


register(
    Action(
        id="predict",
        title="Recalculer les pronostics",
        family="Moteur",
        description=(
            "Prédit les matchs à venir avec les données et les cotes du moment (comme à 07:45 "
            "et 16:45). Les pronostics précédents restent dans l'historique."
        ),
        risk="modifie",
        run=predict,
        exclusive=True,
        cost="aucune requête",
        duration="1 à 20 min",
        params=(
            Param(
                "days_ahead",
                "Jours à venir",
                "int",
                default=DEFAULT_DAYS_AHEAD,
                minimum=1,
                maximum=14,
            ),
        ),
    )
)


async def daily_coupons(ctx: JobContext, params: dict[str, Any]) -> str:
    async with ctx.factory() as session:
        report = await smart_coupon.create_daily(session)
    for profile, state in report.items():
        ctx.log(f"{profile} : {state}")
    ctx.result = report
    return ", ".join(f"{profile} : {state}" for profile, state in report.items()) or "rien"


register(
    Action(
        id="daily_coupons",
        title="Créer les coupons du jour",
        family="Application",
        description=(
            "Enregistre le coupon du jour de chaque profil (comme à 08:05), une seule fois par "
            "jour. Les coupons créés entrent dans l'historique public : ils ne peuvent plus "
            "être retirés."
        ),
        risk="irreversible",
        run=daily_coupons,
        cost="aucune requête",
        duration="moins d'une minute",
    )
)


async def push_test(ctx: JobContext, params: dict[str, Any]) -> str:
    async with ctx.factory() as session:
        return await _push_test(session, params["phone"])


register(
    Action(
        id="push_test",
        title="Notification d'essai",
        family="Comptes",
        description="Envoie une notification d'essai sur les téléphones d'un compte.",
        risk="lecture",
        run=push_test,
        duration="quelques secondes",
        params=(
            Param(
                "phone",
                "Numéro du compte",
                "text",
                default="",
                pattern=r"\+?[0-9 ]{6,20}",
                help="numéro avec l'indicatif, ex. +225 07 00 00 00 00",
            ),
        ),
    )
)


async def coverage(ctx: JobContext, params: dict[str, Any]) -> str:
    async with ctx.factory() as session:
        report = await coverage_report(session)
    ctx.log(format_coverage(report))
    todo = report.get("todo", [])
    return f"{len(todo)} élément(s) à collecter" if todo else "tout est collecté"


register(
    Action(
        id="coverage",
        title="Couverture des données",
        family="Diagnostic",
        description="Ce qui est collecté par championnat et par saison, et ce qui manque.",
        risk="lecture",
        run=coverage,
        duration="quelques secondes",
    )
)


async def quality(ctx: JobContext, params: dict[str, Any]) -> str:
    async with ctx.factory() as session:
        report = await run_quality_checks(session)
    for finding in report["findings"]:
        ctx.log(
            f"{finding['severity']:<7} {finding['competition']:<10} {finding['season']} "
            f"{finding['check']} : {finding['message']}"
        )
    ctx.result = {k: report[k] for k in ("status", "errors", "warnings")}
    return (
        f"{report['status']} : {report['errors']} erreur(s), {report['warnings']} avertissement(s)"
    )


register(
    Action(
        id="quality",
        title="Contrôles de qualité",
        family="Diagnostic",
        description=(
            "Vérifie les données en base : équipes, matchs manquants ou en double, scores, "
            "statistiques incohérentes."
        ),
        risk="lecture",
        run=quality,
        duration="quelques secondes",
    )
)


async def api_quota(ctx: JobContext, params: dict[str, Any]) -> str:
    key = ctx.settings.api_football_key
    if key is None:
        raise AppError("clé API-Football absente (FP_API_FOOTBALL_KEY)")
    async with api_football.ApiFootballClient(
        key.get_secret_value(),
        budget=1,
        min_remaining=0,
        transport=_transport(),
    ) as client:
        status = await client.status()
    requests = status["requests"]
    plan = status.get("subscription", {})
    ctx.result = {
        "used": int(requests["current"]),
        "limit": int(requests["limit_day"]),
        "plan": plan.get("plan"),
        "end": plan.get("end"),
    }
    ctx.log(f"Formule : {plan.get('plan')} (jusqu'au {plan.get('end')})")
    return (
        f"{requests['current']} requêtes utilisées sur {requests['limit_day']} aujourd'hui "
        f"(reste {int(requests['limit_day']) - int(requests['current'])})"
    )


def _transport() -> Any:
    # Même point de substitution que les ingestions (tests sans réseau).
    from footprono.ingestion import service

    return service.api_football_transport


register(
    Action(
        id="api_quota",
        title="Quota API-Football",
        family="Diagnostic",
        description="Requêtes utilisées aujourd'hui et formule de l'abonnement.",
        risk="lecture",
        run=api_quota,
        cost="aucune requête (lecture du compteur)",
        duration="quelques secondes",
    )
)


def history_options() -> list[tuple[str, str]]:
    return [(code, f"{code} · {league.label}") for code, league in history.LEAGUES.items()]


async def collect_history(ctx: JobContext, params: dict[str, Any]) -> str:
    key = ctx.settings.api_football_key
    if key is None:
        raise AppError("clé API-Football absente (FP_API_FOOTBALL_KEY)")
    out = await asyncio.to_thread(ctx.settings.history_archive_dir.expanduser)
    await asyncio.to_thread(out.mkdir, parents=True, exist_ok=True)
    ctx.log(f"Dossier : {out}")
    report = await asyncio.to_thread(
        history.collect,
        key.get_secret_value(),
        params["competitions"],
        out,
        first=params["first_season"],
        reserve=params["reserve"],
        log=ctx.log,
        progress=ctx.progress,
        should_stop=lambda: ctx.stop_requested,
        archive_to=out.parent if params["archive"] else None,
    )
    ctx.result = {
        "used": report.used,
        "remaining": report.remaining,
        "stopped": report.stopped,
        "missing": report.missing,
        "skipped": report.skipped,
        "archive": str(report.archive) if report.archive else None,
    }
    # Compétitions déjà au référentiel : chargées en base aussitôt (rien de redemandé).
    by_api = {c.api_football_id: c.code for c in COMPETITIONS}
    to_import = [
        by_api[history.LEAGUES[code].api_id]
        for code in params["competitions"]
        if history.LEAGUES[code].api_id in by_api and code not in report.skipped
    ]
    imported = ""
    if params["import_after"] and to_import and report.stopped != "admin":
        ctx.log(f"\nImport en base : {', '.join(to_import)}")
        current = max(current_season(c) for c in COMPETITIONS)
        request = IngestionRequest(
            DataSource.API_FOOTBALL,
            to_import,
            list(range(params["first_season"], current + 1)),
            out,
        )
        ingestion = await run_ingestion(ctx.factory, ctx.settings, [request], progress=ctx.log)
        imported = " ; " + _ingestion_summary(ctx, ingestion)
    ctx.check_stop()
    state = {
        "quota": "réserve du jour atteinte, à relancer demain (reprise automatique)",
        None: "terminée",
    }.get(report.stopped, report.stopped or "")
    return (
        f"collecte {state} : {report.used} requêtes, {report.missing} matchs encore sans "
        f"statistiques{imported}"
    )


register(
    Action(
        id="collect_history",
        title="Collecter l'historique API-Football",
        family="Données",
        description=(
            "Télécharge l'historique des compétitions choisies (matchs, journées, statistiques) "
            "pour les études, puis importe en base celles déjà dans l'application. S'arrête "
            "d'elle-même à la réserve du jour ; relancée le lendemain, elle reprend où elle "
            "s'était arrêtée."
        ),
        risk="modifie",
        run=collect_history,
        exclusive=True,
        stoppable=True,
        cost="1 requête par saison + 1 par match terminé (≈ 250 par saison de championnat)",
        duration="plusieurs heures",
        params=(
            Param(
                "competitions",
                "Compétitions (ordre de priorité)",
                "choices",
                default=list(history.LEAGUES),
                options=history_options,
            ),
            Param("first_season", "Depuis la saison", "int", default=2018, minimum=2010),
            Param(
                "reserve",
                "Requêtes laissées au serveur",
                "int",
                default=1500,
                minimum=200,
                help="arrêt quand il ne reste plus que ce nombre de requêtes du jour",
            ),
            Param("archive", "Préparer l'archive à envoyer pour l'étude", "bool", default=True),
            Param("import_after", "Importer en base ensuite", "bool", default=True),
        ),
    )
)
