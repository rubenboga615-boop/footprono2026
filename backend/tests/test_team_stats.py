"""Fiche équipe (stats avancées : Premium) et classement mérité (points réels contre xPts)."""

from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono.football.models import Match

from .conftest import make_premium
from .test_analysis import _signup
from .test_predictions import upcoming  # noqa: F401 (fixture)


async def test_team_profile_free_then_premium(
    db_factory: async_sessionmaker[AsyncSession],
    upcoming: list[int],  # noqa: F811
    client: AsyncClient,
) -> None:
    async with db_factory() as session:
        match = await session.get(Match, upcoming[0])
        assert match is not None
        team_id = match.home_team_id

    assert (await client.get("/api/v1/teams/999999/profile")).status_code == 404

    free = await client.get(f"/api/v1/teams/{team_id}/profile")
    assert free.status_code == 200, free.text
    body = free.json()
    assert body["locked"] is True
    assert (body["competition"], body["season"]) == ("EPL", 2024)
    home, away, total = (body["venues"][v] for v in ("home", "away", "all"))
    assert home["matches"] + away["matches"] == total["matches"] > 20
    assert home["points"] + away["points"] == total["points"]
    assert 0 < total["goals_for"] < 5
    assert total["xg_for"] is None  # masqué
    assert total["corners"] is None
    assert len(body["form"]) == 5
    assert body["seasons"][0] == {"competition": "EPL", "season": 2024,
                                  "played": total["matches"]}  # fmt: skip

    headers = await _signup(client)
    await make_premium(db_factory, "+22997444444")
    premium = (await client.get(f"/api/v1/teams/{team_id}/profile", headers=headers)).json()
    assert premium["locked"] is False
    total = premium["venues"]["all"]
    for field in ("xg_for", "ppda", "corners", "xpts", "shots_on_target"):
        assert total[field] is not None, field

    missing = await client.get(f"/api/v1/teams/{team_id}/profile?season=1990")
    assert missing.status_code == 404


async def test_merited_table_compares_points_and_xpts(
    db_factory: async_sessionmaker[AsyncSession],
    upcoming: list[int],  # noqa: F811
    client: AsyncClient,
) -> None:
    r = await client.get("/api/v1/competitions/epl/seasons/2024/merited")
    assert r.status_code == 200, r.text
    body = r.json()
    table = body["table"]
    assert body["competition"] == "EPL"
    assert len(table) == 20
    assert [t["rank"] for t in table] == list(range(1, 21))
    points = [t["points"] for t in table]
    assert points == sorted(points, reverse=True)
    async with db_factory() as session:
        played = await session.scalar(
            select(text("count(*)")).select_from(Match).where(Match.status == "finished")
        )
    assert sum(t["played"] for t in table) == 2 * played
    assert sorted(t["merited_rank"] for t in table if t["merited_rank"]) == list(
        range(1, 1 + sum(1 for t in table if t["merited_rank"]))
    )
    for t in table:
        if t["xpts"] is None:
            assert t["luck"] is None
            assert t["verdict"] is None
            continue
        assert t["luck"] == round(t["points"] - t["xpts"], 1)
        expected = "lucky" if t["luck"] >= 3 else "unlucky" if t["luck"] <= -3 else "fair"
        assert t["verdict"] == expected

    assert (await client.get("/api/v1/competitions/EPL/seasons/1990/merited")).status_code == 404
