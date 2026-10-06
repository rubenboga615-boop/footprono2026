"""Analyse factuelle d'un match : forme, confrontations, moyennes (Premium)."""

from datetime import UTC, date, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono.accounts.models import User
from footprono.football.models import Match

from .conftest import make_premium
from .test_predictions import upcoming  # noqa: F401 (fixture)


async def _signup(client: AsyncClient) -> dict[str, str]:
    r = await client.post(
        "/api/v1/auth/register",
        json={"phone": "+22997444444", "password": "12345678", "display_name": "Ana",
              "country": "SN", "adult": True},
    )  # fmt: skip
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_analysis_uses_only_past_matches_and_is_premium(
    db_factory: async_sessionmaker[AsyncSession],
    upcoming: list[int],  # noqa: F811
    client: AsyncClient,
) -> None:
    async with db_factory() as session:
        match = await session.get(Match, upcoming[0])
        assert match is not None
        day = match.match_date

    anonymous = await client.get(f"/api/v1/matches/{upcoming[0]}/analysis")
    assert anonymous.status_code == 403

    headers = await _signup(client)
    await make_premium(db_factory, "+22997444444")
    r = await client.get(f"/api/v1/matches/{upcoming[0]}/analysis", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    for side in ("home", "away"):
        form = body["form"][side]
        assert len(form) == 5
        assert all(date.fromisoformat(f["date"]) < day for f in form)
        assert {f["result"] for f in form} <= {"W", "D", "L"}
        dates = [f["date"] for f in form]
        assert dates == sorted(dates, reverse=True)
        season = body["season"][side]
        assert season["matches"] > 20  # fin de saison 2024-25
        assert 0 < season["goals_for"] < 5
        assert season["xg_for"] is not None  # Understat
        assert season["corners"] is not None
    for h2h in body["head_to_head"]:
        assert date.fromisoformat(h2h["date"]) < day

    # Premium terminé : l'analyse n'est plus servie.
    async with db_factory() as session:
        await session.execute(
            update(User).values(premium_until=datetime.now(UTC) - timedelta(minutes=1))
        )
        await session.commit()
        assert await session.scalar(select(User.id)) is not None
    assert (
        await client.get(f"/api/v1/matches/{upcoming[0]}/analysis", headers=headers)
    ).status_code == 403
