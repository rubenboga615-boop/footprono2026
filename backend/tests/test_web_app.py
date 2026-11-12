"""Version web de l'application servie par l'API (FP_WEB_APP_DIR)."""

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from footprono.main import create_app

from .conftest import make_settings


async def test_web_app_served_under_app(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<title>FootProba</title>", encoding="utf-8")
    (tmp_path / "main.dart.js").write_text("// app", encoding="utf-8")
    app = create_app(make_settings(web_app_dir=tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        home = await http.get("/")
        assert home.status_code == 307
        assert home.headers["location"] == "/app/"
        page = await http.get("/app/")
        assert page.status_code == 200
        assert "FootProba" in page.text
        assert (await http.get("/app/main.dart.js")).status_code == 200
        # Audit de sécurité du 12/11/2026, n° 3 : CSP sur la version web, WebSocket du
        # domaine seulement.
        csp = page.headers["content-security-policy"]
        assert "script-src 'self' 'wasm-unsafe-eval'" in csp
        assert "connect-src 'self' wss://test " in csp
        assert "frame-ancestors 'self'" in csp
        assert "object-src 'none'" in csp
        odd = await http.get("/app/", headers={"host": "a.b;script-src *"})
        assert "script-src *" not in odd.headers["content-security-policy"]


def test_web_app_dir_must_contain_index(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match=r"index\.html"):
        create_app(make_settings(web_app_dir=tmp_path))


async def test_no_web_app_by_default() -> None:
    app = create_app(make_settings())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        assert (await http.get("/app/")).status_code == 404


def test_empty_web_app_dir_means_none() -> None:
    assert make_settings(web_app_dir="").web_app_dir is None


def test_csp_allows_only_firebase_loader_scripts(tmp_path: Path) -> None:
    """FlutterFire charge Firebase par un script inline : autorisé par son empreinte (celle
    que Chromium a donnée en le bloquant le 12/11/2026), pas par 'unsafe-inline'."""
    from footprono.main import served_firebase_version, web_csp

    (tmp_path / "main.dart.js").write_bytes(
        b'o=A.aq(j.flutterfire_web_sdk_version)\nif(o==null)o=null\nn=o==null?"12.20.1":o'
    )
    assert served_firebase_version(tmp_path) == "12.20.1"
    assert served_firebase_version(tmp_path / "absent") == "12.19.0"
    csp = web_csp("footproba.example", "12.19.0")
    assert "'sha256-pPjjoSpBd13bHnogATkOaA29BKZz9GGHosqgFMogFpk='" in csp
    assert "unsafe-inline" not in csp.split("style-src")[0]
    assert csp.count("'sha256-") == 6  # app, auth, messaging ; avec et sans Trusted Types
