import logging

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from footprono.core.errors import ServiceUnavailableError


@pytest.fixture
def routes(app: FastAPI) -> None:
    @app.get("/api/v1/_test/boom")
    async def boom() -> None:
        raise RuntimeError("panne interne")

    @app.get("/api/v1/_test/unavailable")
    async def unavailable() -> None:
        raise ServiceUnavailableError("Source de données indisponible")

    @app.get("/api/v1/_test/items/{item_id}")
    async def item(item_id: int) -> dict[str, int]:
        return {"id": item_id}


async def test_unknown_route_uses_error_envelope(client: AsyncClient) -> None:
    response = await client.get("/api/v1/nope")
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "not_found"
    assert error["request_id"] == response.headers["x-request-id"]


@pytest.mark.usefixtures("routes")
async def test_validation_error_envelope(client: AsyncClient) -> None:
    response = await client.get("/api/v1/_test/items/abc")
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"][0]["loc"] == ["path", "item_id"]


@pytest.mark.usefixtures("routes")
async def test_unavailable_dependency_is_explicit(client: AsyncClient) -> None:
    response = await client.get("/api/v1/_test/unavailable")
    assert response.status_code == 503
    assert response.json()["error"] == {
        "code": "service_unavailable",
        "message": "Source de données indisponible",
        "request_id": response.headers["x-request-id"],
    }


@pytest.mark.usefixtures("routes")
async def test_unhandled_error_is_logged_and_hidden(
    client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR):
        response = await client.get("/api/v1/_test/boom")
    assert response.status_code == 500
    error = response.json()["error"]
    assert error["code"] == "internal_error"
    assert "panne interne" not in response.text
    assert any(r.message == "unhandled_error" and r.exc_info for r in caplog.records)
