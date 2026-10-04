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


def test_web_app_dir_must_contain_index(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match=r"index\.html"):
        create_app(make_settings(web_app_dir=tmp_path))


async def test_no_web_app_by_default() -> None:
    app = create_app(make_settings())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        assert (await http.get("/app/")).status_code == 404


def test_empty_web_app_dir_means_none() -> None:
    assert make_settings(web_app_dir="").web_app_dir is None
