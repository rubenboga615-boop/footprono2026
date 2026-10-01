from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from footprono import __version__
from footprono.main import create_app

from .conftest import make_settings


async def test_health_reports_version(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__, "environment": "test"}


async def test_ready_when_dependencies_are_up(client: AsyncClient) -> None:
    response = await client.get("/api/v1/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"]["database"] == {"ok": True, "error": None}
    assert body["checks"]["redis"] == {"ok": True, "error": None}


async def _ready_with(**overrides: object) -> tuple[int, dict[str, object]]:
    app: FastAPI = create_app(make_settings(**overrides))
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as http:
            response = await http.get("/api/v1/ready")
    return response.status_code, response.json()


async def test_ready_reports_unreachable_database() -> None:
    status, body = await _ready_with(
        database_url="postgresql+asyncpg://footprono:footprono@127.0.0.1:1/footprono"
    )
    assert status == 503
    assert body["status"] == "unavailable"
    checks = body["checks"]
    assert isinstance(checks, dict)
    assert checks["database"]["ok"] is False
    assert checks["database"]["error"]
    assert checks["redis"]["ok"] is True


async def test_ready_reports_unreachable_redis() -> None:
    status, body = await _ready_with(redis_url="redis://127.0.0.1:1/0")
    assert status == 503
    checks = body["checks"]
    assert isinstance(checks, dict)
    assert checks["redis"]["ok"] is False
    assert checks["database"]["ok"] is True


async def test_request_id_is_generated(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    request_id = response.headers["x-request-id"]
    assert len(request_id) == 32


async def test_safe_request_id_is_propagated(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health", headers={"x-request-id": "abc-123"})
    assert response.headers["x-request-id"] == "abc-123"


async def test_unsafe_request_id_is_replaced(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health", headers={"x-request-id": "bad id\ninjected"})
    assert response.headers["x-request-id"] != "bad id\ninjected"
    assert len(response.headers["x-request-id"]) == 32


async def test_metrics_expose_route_template(client: AsyncClient) -> None:
    await client.get("/api/v1/health")
    response = await client.get("/metrics")
    assert response.status_code == 200
    assert 'route="/api/v1/health"' in response.text
    assert "footprono_http_requests_total" in response.text


async def test_openapi_contract_is_served(client: AsyncClient) -> None:
    response = await client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/health" in paths
    assert "/api/v1/ready" in paths


def test_route_resolver_maps_templates_and_bounds_labels() -> None:
    from footprono.core.middleware import RouteResolver

    resolver = RouteResolver(lambda: ["/api/v1/matchs/{match_id}", "/metrics"])
    assert resolver.resolve("/api/v1/matchs/42") == "/api/v1/matchs/{match_id}"
    assert resolver.resolve("/metrics") == "/metrics"
    assert resolver.resolve("/n/importe/quoi") == "unmatched"
