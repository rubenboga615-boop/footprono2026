"""Version de l'application Android et téléchargement de l'APK (public)."""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter
from fastapi.responses import FileResponse
from sqlalchemy import func, select

from footprono import app_release
from footprono.api.deps import SessionDep, SettingsDep
from footprono.bookmaker.service import ODDS_MAX_AGE, PLAYABLE_BOOKMAKERS
from footprono.core.errors import NotFoundError
from footprono.football.models import BookmakerOdds

router = APIRouter(tags=["application"])


@router.get("/app/status")
async def status(session: SessionDep) -> dict[str, Any]:
    """État du service pour les joueurs (public) : cotes disponibles ou non. Sans cotes
    récentes (source coupée), ni paris ni coupons du jour : l'application l'explique."""
    seen = await session.scalar(
        select(func.max(BookmakerOdds.last_seen_at)).where(
            BookmakerOdds.bookmaker.in_(PLAYABLE_BOOKMAKERS)
        )
    )
    available = seen is not None and datetime.now(UTC) - seen <= ODDS_MAX_AGE
    return {"odds_available": available, "odds_seen_at": seen}


@router.get("/app/version")
async def version(settings: SettingsDep) -> Any:
    info = app_release.current(settings.app_release_dir)
    if info is None:
        return {"build": 0}
    return {
        "build": info["build"],
        "minimum_build": info.get("minimum_build", 0),
        "notes": info.get("notes", ""),
        "size": info["size"],
        "sha256": info["sha256"],
        "published_at": info["published_at"],
        "download_path": "/api/v1/app/download",
    }


@router.get("/app/download")
async def download(settings: SettingsDep) -> FileResponse:
    info = app_release.current(settings.app_release_dir)
    if info is None:
        raise NotFoundError("aucune version publiée")
    return FileResponse(
        settings.app_release_dir / info["file"],
        media_type="application/vnd.android.package-archive",
        filename=f"footprono-{info['build']}.apk",
    )
