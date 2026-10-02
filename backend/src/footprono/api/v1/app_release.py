"""Version de l'application Android et téléchargement de l'APK (public)."""

from typing import Any

from fastapi import APIRouter
from fastapi.responses import FileResponse

from footprono import app_release
from footprono.api.deps import SettingsDep
from footprono.core.errors import NotFoundError

router = APIRouter(tags=["application"])


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
