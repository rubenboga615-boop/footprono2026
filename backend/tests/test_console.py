"""Console d'administration : catalogue, lancement, journal, conflits, arrêt, collecte."""

import asyncio
import json
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono.accounts import admin
from footprono.accounts import service as accounts
from footprono.console import jobs
from footprono.console.models import AdminJob
from footprono.console.registry import FAMILIES, Action, Param, register
from footprono.ingestion import history
from footprono.notifications.models import Notification

from .conftest import make_settings

Factory = async_sessionmaker[AsyncSession]
API = "/api/v1/admin/console"
PHONE = "+22997111111"


async def _slow(ctx: jobs.JobContext, params: dict[str, Any]) -> str:
    for i in range(params["steps"]):
        ctx.log(f"étape {i + 1}")
        ctx.progress((i + 1) / params["steps"])
        await asyncio.sleep(0.02)
        ctx.check_stop()
    return f"{params['steps']} étapes"


async def _boom(ctx: jobs.JobContext, params: dict[str, Any]) -> str:
    ctx.log("avant l'erreur")
    raise RuntimeError("fichier illisible")


register(
    Action(
        id="test_slow",
        title="Essai lent",
        family="Diagnostic",
        description="essai",
        risk="lecture",
        run=_slow,
        stoppable=True,
        params=(Param("steps", "Étapes", "int", default=3, minimum=1, maximum=500),),
    )
)
register(
    Action(
        id="test_boom", title="Essai en échec", family="Diagnostic", description="essai",
        risk="lecture", run=_boom,
    )
)  # fmt: skip


@pytest.fixture
async def admin_headers(client: AsyncClient, db_factory: Factory) -> dict[str, str]:
    async with db_factory() as session:
        await accounts.register(
            session, make_settings(), phone=PHONE, password="12345678",
            display_name="Admin", country="TG", adult=True,
        )  # fmt: skip
        await session.commit()
    r = await client.post("/api/v1/auth/login", json={"phone": PHONE, "password": "12345678"})
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    # Compte ordinaire : la console est refusée.
    assert (await client.get(f"{API}/actions", headers=headers)).status_code == 403
    async with db_factory() as session:
        await admin.set_role(session, PHONE, "admin")
        await session.commit()
    return headers


def _inline(app: FastAPI) -> list[int]:
    """Exécution directe à la place du worker (les numéros envoyés sont gardés)."""
    sent: list[int] = []

    async def dispatch(job_id: int) -> None:
        sent.append(job_id)
        await jobs.run_job(app.state.session_factory, app.state.settings, job_id)

    app.state.console_dispatch = dispatch
    return sent


def _queue_only(app: FastAPI) -> list[int]:
    sent: list[int] = []

    async def dispatch(job_id: int) -> None:
        sent.append(job_id)

    app.state.console_dispatch = dispatch
    return sent


async def test_catalog_describes_actions(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    assert (await client.get(f"{API}/actions")).status_code == 401
    actions = {
        a["id"]: a for a in (await client.get(f"{API}/actions", headers=admin_headers)).json()
    }
    for expected in (
        "ingest_current", "import_archive", "collect_history", "collect_odds", "predict",
        "daily_coupons", "coverage", "quality", "api_quota", "push_test",
    ):  # fmt: skip
        assert expected in actions
    assert all(a["family"] in FAMILIES for a in actions.values())
    history_action = actions["collect_history"]
    assert history_action["exclusive"]
    assert history_action["stoppable"]
    params = {p["name"]: p for p in history_action["params"]}
    assert params["competitions"]["kind"] == "choices"
    assert {"value": "CAN", "label": "CAN · Coupe d'Afrique des Nations"} in params["competitions"][
        "options"
    ]
    assert params["reserve"] == {
        "name": "reserve", "label": "Requêtes laissées au serveur", "kind": "int",
        "default": 1500, "min": 200,
        "help": "arrêt quand il ne reste plus que ce nombre de requêtes du jour",
    }  # fmt: skip
    assert actions["daily_coupons"]["confirm"] is True
    assert actions["quality"]["confirm"] is False


async def test_job_runs_with_journal_and_notification(
    app: FastAPI, client: AsyncClient, admin_headers: dict[str, str], db_factory: Factory
) -> None:
    sent = _inline(app)
    r = await client.post(
        f"{API}/jobs", json={"action": "test_slow", "params": {"steps": 4}}, headers=admin_headers
    )
    assert r.status_code == 201
    job_id = r.json()["id"]
    assert sent == [job_id]

    detail = (await client.get(f"{API}/jobs/{job_id}", headers=admin_headers)).json()
    assert detail["status"] == "succeeded"
    assert detail["summary"] == "4 étapes"
    assert detail["progress"] == 1.0
    assert detail["params"] == {"steps": 4}
    texts = [line["text"] for line in detail["lines"]]
    assert texts == [
        "Démarrage : Essai lent", "étape 1", "étape 2", "étape 3", "étape 4", "Fin : 4 étapes",
    ]  # fmt: skip
    # Suivi en direct : seulement les lignes pas encore lues.
    after = (
        await client.get(f"{API}/jobs/{job_id}", params={"after": 4}, headers=admin_headers)
    ).json()
    assert [line["n"] for line in after["lines"]] == [5, 6]

    listed = (await client.get(f"{API}/jobs", headers=admin_headers)).json()
    assert [j["id"] for j in listed] == [job_id]
    async with db_factory() as session:
        note = await session.scalar(select(Notification).where(Notification.kind == "admin_job"))
    assert note is not None
    assert note.title == "Console : Essai lent terminée"
    assert note.data == {"job_id": job_id}


async def test_failed_action_is_reported(
    app: FastAPI, client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    _inline(app)
    job = (
        await client.post(f"{API}/jobs", json={"action": "test_boom"}, headers=admin_headers)
    ).json()
    detail = (await client.get(f"{API}/jobs/{job['id']}", headers=admin_headers)).json()
    assert detail["status"] == "failed"
    assert detail["summary"] == "échec : fichier illisible"
    texts = [line["text"] for line in detail["lines"]]
    assert "avant l'erreur" in texts
    assert "RuntimeError: fichier illisible" in texts


async def test_params_are_checked(
    app: FastAPI, client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    sent = _queue_only(app)

    async def post(body: dict[str, Any]) -> httpx.Response:
        return await client.post(f"{API}/jobs", json=body, headers=admin_headers)

    assert (await post({"action": "inconnue"})).status_code == 404
    r = await post({"action": "test_slow", "params": {"steps": 0}})
    assert (r.status_code, r.json()["error"]["message"]) == (422, "« Étapes » : au moins 1")
    assert (await post({"action": "test_slow", "params": {"steps": "3"}})).status_code == 422
    assert (await post({"action": "test_slow", "params": {"autre": 1}})).status_code == 422
    r = await post({"action": "collect_history", "params": {"competitions": ["XXX"]}})
    assert r.status_code == 422
    r = await post({"action": "push_test", "params": {"phone": "pas un numéro"}})
    assert r.status_code == 422
    # Irréversible : refusée sans confirmation explicite.
    r = await post({"action": "daily_coupons"})
    assert (r.status_code, r.json()["error"]["code"]) == (428, "confirmation_required")
    assert sent == []

    r = await post({"action": "collect_history", "params": {"competitions": ["CAN", "SWZ", "CAN"]}})
    assert r.status_code == 201
    # Ordre de priorité du catalogue, sans doublon ; valeurs par défaut complétées.
    assert r.json()["params"] == {
        "competitions": ["SWZ", "CAN"], "first_season": 2018, "reserve": 1500,
        "archive": True, "import_after": True,
    }  # fmt: skip


async def test_conflicts_stop_and_stale_jobs(
    app: FastAPI, client: AsyncClient, admin_headers: dict[str, str], db_factory: Factory
) -> None:
    _queue_only(app)

    async def post(action: str) -> httpx.Response:
        return await client.post(f"{API}/jobs", json={"action": action}, headers=admin_headers)

    big = (await post("collect_history")).json()
    assert big["status"] == "queued"
    # Une seule grosse tâche à la fois ; la même action pas deux fois.
    r = await post("import_archive")
    assert r.status_code == 409
    assert "Collecter l'historique API-Football" in r.json()["error"]["message"]
    assert (await post("collect_history")).status_code == 409
    # Une petite action passe à côté.
    assert (await post("coverage")).status_code == 201

    stopped = await client.post(f"{API}/jobs/{big['id']}/stop", headers=admin_headers)
    assert stopped.json()["status"] == "cancelled"
    assert (
        await client.post(f"{API}/jobs/{big['id']}/stop", headers=admin_headers)
    ).status_code == 409
    second = (await post("import_archive")).json()

    # Sans signe de vie depuis longtemps (redémarrage) : interrompue, ne bloque plus.
    async with db_factory() as session:
        await session.execute(
            update(AdminJob)
            .where(AdminJob.id == second["id"])
            .values(status="running", heartbeat_at=datetime.now(UTC) - timedelta(hours=1))
        )
        await session.commit()
    assert (await post("predict")).status_code == 201
    listed = {j["id"]: j for j in (await client.get(f"{API}/jobs", headers=admin_headers)).json()}
    assert listed[second["id"]]["status"] == "failed"
    assert listed[second["id"]]["summary"] == jobs.INTERRUPTED


async def test_running_job_stops_cleanly(
    app: FastAPI,
    client: AsyncClient,
    admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(jobs, "FLUSH_SECONDS", 0.02)
    _queue_only(app)
    job = (
        await client.post(
            f"{API}/jobs",
            json={"action": "test_slow", "params": {"steps": 500}},
            headers=admin_headers,
        )
    ).json()
    task = asyncio.create_task(
        jobs.run_job(app.state.session_factory, app.state.settings, job["id"])
    )
    for _ in range(200):
        detail = (await client.get(f"{API}/jobs/{job['id']}", headers=admin_headers)).json()
        if detail["lines"]:
            break
        await asyncio.sleep(0.02)
    assert detail["status"] == "running"
    r = await client.post(f"{API}/jobs/{job['id']}/stop", headers=admin_headers)
    assert r.json()["stop_requested"] is True
    assert await asyncio.wait_for(task, 10) == "cancelled"
    detail = (await client.get(f"{API}/jobs/{job['id']}", headers=admin_headers)).json()
    assert detail["summary"] == "arrêtée à la demande de l'administrateur"
    assert 0 < detail["progress"] < 1

    # Message redistribué après un arrêt brutal : jamais exécuté une seconde fois.
    assert await jobs.run_job(app.state.session_factory, app.state.settings, job["id"]) == (
        "cancelled"
    )


async def test_redelivered_running_job_is_interrupted(
    app: FastAPI, client: AsyncClient, admin_headers: dict[str, str], db_factory: Factory
) -> None:
    _queue_only(app)
    job = (
        await client.post(f"{API}/jobs", json={"action": "test_slow"}, headers=admin_headers)
    ).json()
    async with db_factory() as session:
        await session.execute(
            update(AdminJob).where(AdminJob.id == job["id"]).values(status="running")
        )
        await session.commit()
    assert await jobs.run_job(db_factory, make_settings(), job["id"]) == "failed"
    detail = (await client.get(f"{API}/jobs/{job['id']}", headers=admin_headers)).json()
    assert detail["summary"] == jobs.INTERRUPTED


async def test_dashboard(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    board = (await client.get(f"{API}/dashboard", headers=admin_headers)).json()
    assert board["services"]["database"] is True
    assert board["services"]["redis"] is True
    assert board["users"] == {"total": 1, "premium": 1}  # essai Premium à l'inscription
    assert board["last"]["ingestion"] is None
    assert board["coupons_today"] == {"count": 0, "missing_codes": []}
    texts = [t["text"] for t in board["todo"]]
    assert "pas de relevé de cotes depuis plus de 7 h" in texts


# --- Collecte de l'historique (sans réseau) ----------------------------------


def _league(league_id: int, country: str, name: str, years: list[int]) -> dict[str, Any]:
    return {
        "league": {"id": league_id, "name": name},
        "country": {"name": country},
        "seasons": [
            {"year": y, "coverage": {"fixtures": {"statistics_fixtures": True}}} for y in years
        ],
    }


def _fixture(fid: int, status: str = "FT", rnd: str = "Regular Season - 1") -> dict[str, Any]:
    return {"fixture": {"id": fid, "status": {"short": status}}, "league": {"round": rnd}}


class FakeApi:
    def __init__(self, remaining: int = 7000) -> None:
        self.remaining = remaining
        self.calls: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["x-apisports-key"] == "cle-test"
        path, params = request.url.path, dict(request.url.params)
        self.calls.append(f"{path} {json.dumps(params, sort_keys=True)}")
        self.remaining -= 1
        if path == "/leagues":
            body = {
                "207": [_league(207, "Switzerland", "Super League", [2023, 2024, 2025])],
                "6": [_league(6, "World", "Africa Cup of Nations", [2023, 2025])],
                "119": [_league(119, "Spain", "La Liga", [2025])],  # mauvais identifiant
            }[params["id"]]
        elif path == "/fixtures":
            base = int(params["season"]) * 10
            body = [_fixture(base + 1), _fixture(base + 2), _fixture(base + 3, "NS")]
        else:
            body = [{"team": {"id": 1}, "statistics": [{"type": "Total Shots", "value": 9}]}]
        return httpx.Response(
            200,
            json={"errors": [], "response": body},
            headers={"x-ratelimit-requests-remaining": str(self.remaining)},
        )


def test_history_collection_resumes_and_respects_reserve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(history, "PAUSE_SECONDS", 0)
    api = FakeApi()
    monkeypatch.setattr(history, "transport", httpx.MockTransport(api))
    out = tmp_path / "api-football-historique"
    lines: list[str] = []
    today = date(2026, 10, 4)

    report = history.collect(
        "cle-test", ["SWZ", "CAN", "DNK"], out, first=2023, reserve=100,
        log=lines.append, archive_to=tmp_path, today=today,
    )  # fmt: skip
    assert report.stopped is None
    assert report.skipped == ["DNK"]
    assert any("l'identifiant 119 est « Spain · La Liga »" in line for line in lines)
    # Suisse : statistiques des matchs terminés ; CAN : résultats seulement.
    stats = out / "SWZ" / "2024" / "statistics.jsonl"
    assert [json.loads(row)["fixture"] for row in stats.read_text().splitlines()] == [20241, 20242]
    assert not (out / "CAN" / "2023" / "statistics.jsonl").exists()
    assert (out / "CAN" / "2025" / "fixtures.json").exists()
    assert sum(c.startswith("/fixtures/statistics") for c in api.calls) == 6
    assert report.missing == 0
    assert report.archive == tmp_path / "api-football-historique-20261004.tar.gz"
    assert report.archive.exists()
    summary = (out / "RESUME.txt").read_text()
    assert "SWZ · Suisse · Super League" in summary
    assert "2023 : 3 matchs, 2 terminés, résultats seulement" in summary

    # Reprise : rien de redemandé, sauf la liste des matchs des deux dernières saisons.
    stamp = datetime(2026, 10, 4, 12).timestamp()
    for info in out.glob("*/league.json"):
        os.utime(info, (stamp, stamp))
    api.calls.clear()
    history.collect(
        "cle-test", ["SWZ", "CAN"], out, first=2023, reserve=100, log=lines.append, today=today
    )
    assert sorted(api.calls) == [
        '/fixtures {"league": "207", "season": "2025"}',
        '/fixtures {"league": "6", "season": "2025"}',
    ]


def test_history_collection_stops_at_reserve_and_on_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(history, "PAUSE_SECONDS", 0)
    api = FakeApi(remaining=106)
    monkeypatch.setattr(history, "transport", httpx.MockTransport(api))
    out = tmp_path / "h"
    report = history.collect("cle-test", ["SWZ"], out, first=2023, reserve=100, log=lambda _m: None)
    # 1 (ligue) + 3 (saisons) + 2 statistiques : il reste 100, la réserve est atteinte.
    assert report.stopped == "quota"
    assert report.used == 6
    assert report.missing == 4

    calls = 0

    def stop() -> bool:
        nonlocal calls
        calls += 1
        return calls > 2

    api.remaining = 7000
    report = history.collect(
        "cle-test", ["SWZ"], out, first=2023, reserve=100, log=lambda _m: None, should_stop=stop
    )
    assert report.stopped == "admin"
    assert report.missing == 3


async def test_console_pages_are_served_with_strict_headers(client: AsyncClient) -> None:
    r = await client.get("/admin")
    assert (r.status_code, r.headers["location"]) == (307, "/admin/")
    page = await client.get("/admin/")
    assert page.status_code == 200
    assert '<script src="admin.js" defer></script>' in page.text
    assert "script-src 'self'" in page.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
    assert page.headers["x-frame-options"] == "DENY"
    assert page.headers["cache-control"] == "no-store"
    script = await client.get("/admin/admin.js")
    assert script.status_code == 200
    assert "/admin/console" in script.text
    # Aucune donnée insérée en HTML brut.
    assert "innerHTML" not in script.text
