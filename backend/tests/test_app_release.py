"""Mise à jour de l'application : publication de l'APK, version, téléchargement."""

import json
import zipfile
from pathlib import Path

import pytest
from httpx import AsyncClient

from footprono import app_release
from footprono.accounts.cli import main as admin_main
from footprono.core.config import Settings
from footprono.core.errors import AppError

from .conftest import make_settings


def _archive(tmp: Path, build: int, apk: bytes = b"APK") -> Path:
    path = tmp / f"footprono-apk-{build}.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(app_release.APK_IN_ZIP, apk)
        z.writestr("app-armeabi-v7a-release.apk", b"old phones")
        z.writestr(app_release.RELEASE, json.dumps({"build": build}))
    return path


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(app_release_dir=tmp_path / "app")


async def test_no_release_yet(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/app/version")).json() == {"build": 0}
    assert (await client.get("/api/v1/app/download")).status_code == 404


async def test_publish_then_download(
    client: AsyncClient, settings: Settings, tmp_path: Path
) -> None:
    info = app_release.publish(_archive(tmp_path, 42, b"v42"), settings.app_release_dir, "Nouveau")
    assert (info["build"], info["file"]) == (42, "footprono-42.apk")

    version = (await client.get("/api/v1/app/version")).json()
    assert version["build"] == 42
    assert version["notes"] == "Nouveau"
    assert version["download_path"] == "/api/v1/app/download"
    apk = await client.get("/api/v1/app/download")
    assert apk.status_code == 200
    assert apk.content == b"v42"
    assert apk.headers["content-type"] == "application/vnd.android.package-archive"

    # Jamais de retour en arrière, ni de republication du même numéro.
    with pytest.raises(AppError, match="déjà publiée"):
        app_release.publish(_archive(tmp_path, 42), settings.app_release_dir)
    for build in (43, 44, 45):
        app_release.publish(_archive(tmp_path, build), settings.app_release_dir, minimum_build=40)
    kept = sorted(p.name for p in settings.app_release_dir.glob("*.apk"))
    assert kept == ["footprono-44.apk", "footprono-45.apk"]  # avant-dernière gardée
    assert (await client.get("/api/v1/app/version")).json()["minimum_build"] == 40


def test_publish_command_rejects_wrong_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("FP_APP_RELEASE_DIR", str(tmp_path / "app"))
    (tmp_path / "x.txt").write_text("pas une archive")
    assert admin_main(["publish-apk", str(tmp_path / "x.txt")]) == 1
    assert "n'est pas l'archive" in capsys.readouterr().err
