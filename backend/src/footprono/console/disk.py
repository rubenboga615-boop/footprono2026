"""Espace disque : ce qui prend de la place sur le serveur et à quelle vitesse ça grossit.

Lecture seule (retour du fondateur du 24/11/2026 : « le stockage se remplit très vite »).
Fichiers bruts des sources, fichiers de la console, sauvegardes, base de données (tables
les plus lourdes), et croissance des fichiers bruts sur les 7 derniers jours par origine.
"""

import os
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.core.config import Settings
from footprono.football.models import RawFile

GB = 1e9


def folder_size(path: Path) -> tuple[int, int]:
    """(octets, fichiers) d'un dossier, sous-dossiers compris ; (0, 0) s'il n'existe pas."""
    total = count = 0
    if not path.exists():
        return 0, 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
                count += 1
            except OSError:
                continue
    return total, count


def _children(path: Path) -> list[tuple[str, int, int]]:
    """Taille de chaque sous-dossier direct (et des fichiers posés à la racine)."""
    if not path.exists():
        return []
    out: list[tuple[str, int, int]] = []
    loose = loose_n = 0
    for child in sorted(path.iterdir()):
        if child.is_dir():
            size, n = folder_size(child)
            out.append((child.name, size, n))
        else:
            try:
                loose += child.stat().st_size
                loose_n += 1
            except OSError:
                continue
    if loose_n:
        out.append(("(fichiers à la racine)", loose, loose_n))
    return sorted(out, key=lambda r: -r[1])


def _origin_kind(origin: str) -> str:
    """Regroupe les origines des fichiers bruts : cotes, direct, calendriers, statistiques…"""
    for needle, label in (
        ("/odds", "cotes"),
        ("fixtures?ids=", "direct et matchs complétés"),
        ("/injuries", "blessés"),
        ("/fixtures/statistics", "statistiques de match"),
        ("/fixtures?league", "calendriers"),
        ("football-data", "football-data"),
        ("understat", "Understat"),
    ):
        if needle in origin:
            return label
    return "autres"


async def disk_report(session: AsyncSession, settings: Settings, now: datetime) -> dict[str, Any]:
    report: dict[str, Any] = {}
    try:
        usage = shutil.disk_usage(settings.raw_data_dir if settings.raw_data_dir.exists() else ".")
        report["disk"] = {"total": usage.total, "used": usage.used, "free": usage.free}
    except OSError:
        report["disk"] = None
    folders = {
        "fichiers bruts des sources": settings.raw_data_dir,
        "fichiers de la console (exports, rapports)": settings.console_files_dir,
        "historique API-Football (archive)": settings.history_archive_dir.expanduser(),
        "APK publiées": settings.app_release_dir,
        "versions web publiées": settings.web_release_dir,
    }
    if settings.backups_dir is not None:
        folders["sauvegardes de la base"] = settings.backups_dir
    report["folders"] = {label: folder_size(path) for label, path in folders.items()}
    report["raw_children"] = []
    for child in _children(settings.raw_data_dir):
        report["raw_children"].append(child)
    report["database"] = await session.scalar(text("SELECT pg_database_size(current_database())"))
    tables = await session.execute(
        text(
            "SELECT relname, pg_total_relation_size(c.oid) AS size, reltuples::bigint "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind = 'r' ORDER BY size DESC LIMIT 10"
        )
    )
    report["tables"] = [(name, int(size), int(rows)) for name, size, rows in tables.all()]
    since = now - timedelta(days=7)
    rows = await session.execute(
        select(RawFile.origin, func.count(), func.sum(RawFile.size_bytes))
        .where(RawFile.fetched_at >= since)
        .group_by(RawFile.origin)
    )
    growth: dict[str, list[int]] = {}
    for origin, n, size in rows.tuples():
        g = growth.setdefault(_origin_kind(origin), [0, 0])
        g[0] += int(n)
        g[1] += int(size or 0)
    report["raw_growth_7d"] = sorted(growth.items(), key=lambda kv: -kv[1][1])
    return report


def _gb(n: float) -> str:
    return f"{n / GB:.2f} Go"


def format_report(report: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    disk = report.get("disk")
    if disk:
        lines.append(
            f"Disque : {_gb(disk['used'])} utilisés sur {_gb(disk['total'])}, "
            f"{_gb(disk['free'])} libres"
        )
    lines.append(f"Base de données : {_gb(report['database'] or 0)}")
    for name, size, rows in report["tables"]:
        lines.append(f"  {name} : {_gb(size)} ({rows:,} lignes)".replace(",", " "))
    lines.append("Dossiers :")
    for label, (size, n) in report["folders"].items():
        lines.append(f"  {label} : {_gb(size)} ({n} fichiers)")
    if report["raw_children"]:
        lines.append("Fichiers bruts, par source :")
        for name, size, n in report["raw_children"]:
            lines.append(f"  {name} : {_gb(size)} ({n} fichiers)")
    growth = report["raw_growth_7d"]
    if growth:
        total = sum(g[1] for _, g in growth)
        lines.append(
            f"Fichiers bruts ajoutés ces 7 derniers jours : {_gb(total)} "
            f"(environ {_gb(total / 7)} par jour)"
        )
        for kind, (n, size) in growth:
            lines.append(f"  {kind} : {_gb(size)} ({n} fichiers, {_gb(size / 7)} par jour)")
    disk = report.get("disk")
    if disk and growth:
        per_day = sum(g[1] for _, g in growth) / 7
        if per_day > 0:
            lines.append(
                f"À ce rythme (fichiers bruts seulement), disque plein dans environ "
                f"{disk['free'] / per_day:.0f} jours"
            )
    return lines


async def run(session: AsyncSession, settings: Settings) -> tuple[dict[str, Any], list[str]]:
    report = await disk_report(session, settings, datetime.now(UTC))
    return report, format_report(report)
