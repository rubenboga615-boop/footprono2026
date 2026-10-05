"""Console v2 : fichiers, versions de l'application, comptes, frise des tâches, études."""

import io
import json
import sys
import tarfile
import time
import zipfile
from pathlib import Path
from typing import Any

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono import app_release
from footprono.accounts import admin
from footprono.accounts import service as accounts
from footprono.console import actions, runs, studies
from footprono.console.jobs import JobContext, JobStoppedError
from footprono.core.config import Settings

from .conftest import TEST_REDIS_URL, make_settings

Factory = async_sessionmaker[AsyncSession]
API = "/api/v1/admin/console"
PHONE = "+22997111111"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(app_release_dir=tmp_path / "app", console_files_dir=tmp_path / "files")


@pytest.fixture
async def headers(client: AsyncClient, db_factory: Factory) -> dict[str, str]:
    async with db_factory() as session:
        await accounts.register(
            session, make_settings(), phone=PHONE, password="12345678",
            display_name="Admin", country="TG", adult=True,
        )  # fmt: skip
        await admin.set_role(session, PHONE, "admin")
        await session.commit()
    r = await client.post("/api/v1/auth/login", json={"phone": PHONE, "password": "12345678"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_files_are_listed_and_downloaded_by_signed_link(
    client: AsyncClient, headers: dict[str, str], settings: Settings
) -> None:
    folder = settings.console_files_dir
    folder.mkdir(parents=True)
    (folder / "footproba-donnees-20261005.dump").write_bytes(b"donnees")
    (folder / "cache-football-data").mkdir()  # cache d'une action : jamais listé
    (folder / "apk-1234.part").write_bytes(b"envoi en cours")

    listed = (await client.get(f"{API}/files", headers=headers)).json()
    assert [f["name"] for f in listed] == ["footproba-donnees-20261005.dump"]
    assert listed[0]["size"] == 7

    assert (await client.post(f"{API}/files/../secret/link", headers=headers)).status_code == 404
    link = (
        await client.post(f"{API}/files/footproba-donnees-20261005.dump/link", headers=headers)
    ).json()["url"]
    assert link.startswith("/api/v1/admin/console/download/footproba-donnees-20261005.dump?")
    # Sans en-tête d'authentification : le lien signé suffit.
    got = await client.get(link)
    assert got.status_code == 200
    assert got.content == b"donnees"
    assert "attachment" in got.headers["content-disposition"]
    forged = link.replace("signature=", "signature=0")
    assert (await client.get(forged)).status_code == 403
    expired = (
        "/api/v1/admin/console/download/footproba-donnees-20261005.dump"
        f"?expires={int(time.time()) - 10}&signature=x"
    )
    assert (await client.get(expired)).status_code == 403

    deleted = await client.delete(f"{API}/files/footproba-donnees-20261005.dump", headers=headers)
    assert deleted.status_code == 204
    assert (await client.get(f"{API}/files", headers=headers)).json() == []


def _archive(build: int) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr(app_release.APK_IN_ZIP, b"APK")
        z.writestr(app_release.RELEASE, json.dumps({"build": build}))
    return buffer.getvalue()


async def test_app_release_is_published_from_the_console(
    client: AsyncClient, headers: dict[str, str], settings: Settings
) -> None:
    assert (await client.get(f"{API}/app-release", headers=headers)).json() == {"current": None}
    r = await client.post(
        f"{API}/app-release",
        params={"notes": "FootProba : nouveau nom", "minimum": 70},
        content=_archive(78),
        headers={**headers, "Content-Type": "application/octet-stream"},
    )
    assert r.status_code == 200
    current = r.json()["current"]
    assert (current["build"], current["notes"], current["minimum_build"]) == (
        78, "FootProba : nouveau nom", 70,
    )  # fmt: skip
    assert (await client.get("/api/v1/app/version")).json()["build"] == 78
    # Archive invalide : refusée, rien de publié, aucun fichier temporaire laissé.
    bad = await client.post(
        f"{API}/app-release", content=b"pas une archive",
        headers={**headers, "Content-Type": "application/octet-stream"},
    )  # fmt: skip
    assert bad.status_code == 400
    assert not list(settings.console_files_dir.glob("*.part"))
    again = await client.post(
        f"{API}/app-release", content=_archive(78),
        headers={**headers, "Content-Type": "application/octet-stream"},
    )  # fmt: skip
    assert "déjà publiée" in again.json()["error"]["message"]


async def test_accounts_admin_role_phone_and_temporary_password(
    client: AsyncClient, headers: dict[str, str], db_factory: Factory
) -> None:
    async with db_factory() as session:
        player = await accounts.register(
            session, make_settings(), phone="+22997222222", password="abcdefgh",
            display_name="Kofi", country="TG", adult=True,
        )  # fmt: skip
        await session.commit()
        player_id = player.id
    me = (await client.get("/api/v1/me", headers=headers)).json()

    refused = await client.post(
        f"/api/v1/admin/users/{me['id']}/role", json={"role": "user"}, headers=headers
    )
    assert refused.status_code == 400  # jamais son propre rôle : pas de console sans admin
    made = await client.post(
        f"/api/v1/admin/users/{player_id}/role", json={"role": "admin"}, headers=headers
    )
    assert made.json()["role"] == "admin"

    moved = await client.post(
        f"/api/v1/admin/users/{player_id}/phone",
        json={"phone": "+229 61 00 00 00"},
        headers=headers,
    )
    assert moved.json()["phone"] == "+22961000000"
    taken = await client.post(
        f"/api/v1/admin/users/{player_id}/phone", json={"phone": PHONE}, headers=headers
    )
    assert taken.status_code == 400

    reset = await client.post(f"/api/v1/admin/users/{player_id}/password-reset", headers=headers)
    password = reset.json()["password"]
    assert len(password) >= 12
    login = await client.post(
        "/api/v1/auth/login", json={"phone": "+22961000000", "password": password}
    )
    assert login.status_code == 200
    old = await client.post(
        "/api/v1/auth/login", json={"phone": "+22961000000", "password": "abcdefgh"}
    )
    assert old.status_code == 401


async def test_payments_list(client: AsyncClient, headers: dict[str, str]) -> None:
    assert (await client.get(f"{API}/payments", headers=headers)).json() == []


async def test_scheduled_task_runs_feed_the_timeline(monkeypatch: pytest.MonkeyPatch) -> None:
    import redis
    from redis.asyncio import Redis

    sync = redis.Redis.from_url(TEST_REDIS_URL)
    monkeypatch.setattr(runs, "_client", sync)
    sync.delete(runs.PREFIX + "collect_odds", runs.PREFIX + "follow_live")

    @runs.tracked("collect_odds")
    def odds() -> dict[str, Any]:
        return {"status": "partial"}

    @runs.tracked("follow_live")
    def live() -> dict[str, Any]:
        raise RuntimeError("API injoignable")

    assert odds() == {"status": "partial"}
    with pytest.raises(RuntimeError):
        live()
    client = Redis.from_url(TEST_REDIS_URL)
    try:
        timeline = {t["task"]: t for t in await runs.recent_runs(client)}
    finally:
        await client.aclose()
    assert [r["status"] for r in timeline["collect_odds"]["runs"]] == ["warning"]
    assert [r["status"] for r in timeline["follow_live"]["runs"]] == ["error"]
    assert timeline["collect_odds"]["label"] == "Cotes (3 h)"


class _Ctx(JobContext):
    """Contexte sans base : journal en mémoire."""

    def __init__(self, settings: Settings) -> None:
        super().__init__(None, settings, 1)  # type: ignore[arg-type]
        self.lines: list[str] = []

    def log(self, message: str) -> None:
        self.lines.extend(str(message).splitlines())


async def test_run_process_streams_output_and_stops_on_request(
    settings: Settings, tmp_path: Path
) -> None:
    ctx = _Ctx(settings)
    out = tmp_path / "rapport.txt"
    code = await actions.run_process(
        ctx,
        [sys.executable, "-c", "import sys; print('ligne 1'); print('erreur', file=sys.stderr)"],
        stdout_to=out,
    )
    assert code == 0
    assert out.read_text() == "ligne 1\n"
    assert sorted(ctx.lines) == ["erreur", "ligne 1"]

    ctx.stop_requested = True
    with pytest.raises(JobStoppedError):
        await actions.run_process(ctx, [sys.executable, "-c", "import time; time.sleep(30)"])


def _fake_api(request: httpx.Request) -> httpx.Response:
    path, params = request.url.path, dict(request.url.params)
    if path == "/odds":
        body: Any = [
            {
                "fixture": {"id": 1, "date": "2026-10-10T19:00:00+00:00"},
                "update": "2026-10-05T08:00:00+00:00",
                "bookmakers": [{"bets": [{"name": "Match Winner", "values": [
                    {"value": "Home", "odd": "1.90"}, {"value": "Draw", "odd": "3.40"},
                    {"value": "Away", "odd": "4.10"},
                ]}]}],
            }
        ]  # fmt: skip
        return httpx.Response(200, json={"errors": [], "results": 1, "response": body})
    if path == "/leagues":
        return httpx.Response(200, json={"errors": [], "response": [{
            "league": {"name": "Ekstraklasa"}, "country": {"name": "Poland"},
            "seasons": [{"year": 2025, "coverage": {"fixtures": {"statistics_fixtures": True}}}],
        }]})  # fmt: skip
    if path == "/teams":
        assert params["season"] == "2025"
        return httpx.Response(200, json={"errors": [], "response": [
            {"team": {"id": 2, "name": "Legia"}}, {"team": {"id": 1, "name": "Lech"}},
        ]})  # fmt: skip
    if "football-data" in str(request.url):
        if request.url.path.endswith("P1.csv") or request.url.path.endswith("NOR.csv"):
            return httpx.Response(200, content=b"HomeTeam,AwayTeam,HS,Referee\nA,B,10,X\n")
        return httpx.Response(404)
    return httpx.Response(404)


def test_studies_without_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(studies, "transport", httpx.MockTransport(_fake_api))
    monkeypatch.setattr(studies, "PAUSE_SECONDS", 0)
    lines: list[str] = []

    odds = studies.check_odds("cle", 61, 2026, lines.append)
    assert odds["results"] == 1
    assert "   1xBet 1-N-2 : Home 1.90 / Draw 3.40 / Away 4.10" in lines

    out = tmp_path / "equipes.json"
    studies.api_football_teams("cle", [106], 2025, out, lines.append)
    data = json.loads(out.read_text())
    season = data["leagues"]["106"]["seasons"]["2025"]
    assert [t["name"] for t in season["teams"]] == ["Lech", "Legia"]
    assert season["coverage"]["statistiques"] is True

    archive = tmp_path / "fd.tar.gz"
    done = studies.football_data_files(
        ["P1", "NOR"], 2025, tmp_path / "cache", archive, lines.append
    )
    assert done >= 2
    with tarfile.open(archive) as tar:
        names = tar.getnames()
    assert "football-data/RESUME.txt" in names
    assert "football-data/autres/NOR.csv" in names
    assert any(n.startswith("football-data/principaux/P1/") for n in names)
