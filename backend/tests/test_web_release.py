"""Version web (iPhone, ordinateur) publiée depuis la console et servie sur /app."""

import io
import json
import zipfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono import web_release
from footprono.accounts import admin
from footprono.accounts import service as accounts
from footprono.accounts.cli import main as admin_main
from footprono.core.config import Settings
from footprono.core.errors import AppError
from footprono.main import create_app

from .conftest import make_settings

API = "/api/v1/admin/console"
PHONE = "+22997111112"
INDEX = '<!DOCTYPE html><base href="/app/"><title>FootProba {}</title>'


def _site(version: str, extra: dict[str, bytes] | None = None, index: str = INDEX) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("index.html", index.format(version))
        z.writestr("flutter_bootstrap.js", "// chargeur")
        z.writestr("main.dart.js", f"// application {version}")
        z.writestr("assets/fonts/x.ttf", b"police")
        z.writestr("release.json", json.dumps({"build": 90}))
        for name, data in (extra or {}).items():
            z.writestr(name, data)
    return buffer.getvalue()


def _file(tmp: Path, data: bytes) -> Path:
    path = tmp / "footprono-web.zip"
    path.write_bytes(data)
    return path


def test_publish_switches_versions_and_keeps_one_back(tmp_path: Path) -> None:
    root = tmp_path / "web"
    assert web_release.current(root) is None
    for version in ("A", "B", "C"):
        web_release.publish(_file(tmp_path, _site(version)), root)
        served = web_release.served_dir(root)
        assert f"FootProba {version}" in (served / "index.html").read_text()
    assert len(list(root.glob("web-*"))) == 2  # la dernière et l'avant-dernière
    info = web_release.current(root)
    assert info is not None
    assert info["build"] == 90
    assert info["published_at"]


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"pas une archive", "footprono-web.zip"),
        (_site("A", {"../evasion.js": b"x"}), "chemin refusé"),
        (_site("A", index="<title>{}</title>"), "--base-href"),
    ],
)
def test_bad_archives_are_refused(tmp_path: Path, data: bytes, message: str) -> None:
    with pytest.raises(AppError, match=message):
        web_release.publish(_file(tmp_path, data), tmp_path / "web")
    assert web_release.current(tmp_path / "web") is None


def test_apk_archive_is_not_a_web_version(tmp_path: Path) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("app-arm64-v8a-release.apk", b"APK")
    with pytest.raises(AppError, match="footprono-apk"):
        web_release.publish(_file(tmp_path, buffer.getvalue()), tmp_path / "web")


async def test_published_version_is_served_without_stale_cache(tmp_path: Path) -> None:
    root = tmp_path / "web"
    app = create_app(make_settings(web_release_dir=root))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        # Rien de publié : pas d'erreur serveur, juste rien à montrer.
        assert (await http.get("/app/")).status_code == 404
        assert (await http.get("/")).status_code == 404
        web_release.publish(_file(tmp_path, _site("A")), root)
        page = await http.get("/app/")
        assert page.status_code == 200
        assert "FootProba A" in page.text
        assert page.headers["cache-control"] == "no-cache"
        assert (await http.get("/")).headers["location"] == "/app/"
        assert (await http.get("/app/main.dart.js")).text == "// application A"


def test_cli_publish_web(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FP_WEB_RELEASE_DIR", str(tmp_path / "web"))
    from footprono.core.config import get_settings

    get_settings.cache_clear()
    try:
        assert admin_main(["publish-web", str(_file(tmp_path, _site("A")))]) == 0
        assert admin_main(["publish-web", str(_file(tmp_path, b"rien"))]) == 1
    finally:
        get_settings.cache_clear()
    assert web_release.current(tmp_path / "web") is not None


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(web_release_dir=tmp_path / "web", console_files_dir=tmp_path / "files")


async def test_web_version_is_published_from_the_console(
    client: AsyncClient,
    db_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    async with db_factory() as session:
        await accounts.register(
            session, make_settings(), phone=PHONE, password="12345678",
            display_name="Admin", country="CI", adult=True,
        )  # fmt: skip
        await admin.set_role(session, PHONE, "admin")
        await session.commit()
    login = await client.post(
        "/api/v1/auth/console-login", json={"phone": PHONE, "password": "12345678"}
    )
    headers = {
        "Authorization": f"Bearer {login.json()['access_token']}",
        "Content-Type": "application/octet-stream",
    }
    assert (await client.get(f"{API}/web-release", headers=headers)).json() == {"current": None}
    r = await client.post(f"{API}/web-release", content=_site("A"), headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["current"]["build"] == 90
    assert (await client.get("/app/")).status_code == 200
    bad = await client.post(f"{API}/web-release", content=b"rien", headers=headers)
    assert bad.status_code == 400
    assert not list(settings.console_files_dir.glob("*.part"))
    # Réservé à l'administrateur.
    assert (await client.post(f"{API}/web-release", content=_site("B"))).status_code == 401
