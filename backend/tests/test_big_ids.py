"""Audit du 20/11/2026 (point 10, déjà relevé le 14/11) : un identifiant trop grand dans une
adresse renvoyait une erreur 500 au lieu de « introuvable »."""

import pytest
from httpx import AsyncClient

HUGE = "99999999999999999999"


@pytest.mark.parametrize(
    "path",
    [
        f"/api/v1/matches/{HUGE}",
        f"/api/v1/matches/{HUGE}/picks",
        f"/api/v1/matches/{HUGE}/offer",
        f"/api/v1/teams/{HUGE}",
        "/api/v1/matches/2147483648",
    ],
)
async def test_huge_ids_are_not_found(client: AsyncClient, path: str) -> None:
    r = await client.get(path)
    assert r.status_code in (404, 422), r.text
