"""Fiche arbitre : cartons par match contre la moyenne du championnat, mêmes saisons."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono.football.models import Match, MatchStatus
from footprono.football.referees import MIN_MATCHES, referee_key

from .test_predictions import upcoming  # noqa: F401 (fixture)


def test_referee_key_merges_spellings() -> None:
    assert referee_key("Stuart Attwell") == referee_key("S. Attwell") == referee_key("S Attwell")
    assert referee_key("Jesús Gil Manzano") == referee_key("J. Gil Manzano") == "j gil manzano"
    assert referee_key("Stuart Attwell") != referee_key("Simon Hooper")


async def test_referee_table_and_profile(
    db_factory: async_sessionmaker[AsyncSession],
    upcoming: list[int],  # noqa: F811
    client: AsyncClient,
) -> None:
    async with db_factory() as session:
        finished = (
            await session.scalars(select(Match).where(Match.status == MatchStatus.FINISHED))
        ).all()
        taylor = [m for m in finished if m.referee == "A Taylor"]
        # Même arbitre écrit à la façon d'API-Football sur un match : une seule fiche.
        await session.execute(
            update(Match).where(Match.id == taylor[0].id).values(api_referee="Anthony Taylor")
        )
        await session.commit()
    cards = [m.home_yellow_cards + m.away_yellow_cards for m in finished]  # type: ignore[operator]

    r = await client.get("/api/v1/competitions/epl/seasons/2024/referees")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["matches"] == len(finished)
    assert body["league_yellow"] == pytest.approx(sum(cards) / len(cards), abs=0.01)
    assert body["without_referee"] == 0
    refs = body["referees"]
    assert sum(x["matches"] for x in refs) == len(finished)
    ranked = [x for x in refs if x["enough"]]
    assert all(x["matches"] >= MIN_MATCHES for x in ranked)
    assert [x["yellow"] for x in ranked] == sorted((x["yellow"] for x in ranked), reverse=True)
    assert refs[: len(ranked)] == ranked  # peu de matchs : à la fin
    names = [x["name"] for x in refs]
    assert "Anthony Taylor" in names
    assert "A Taylor" not in names

    profile = (await client.get("/api/v1/referees/profile", params={"name": "A Taylor"})).json()
    assert profile["name"] == "Anthony Taylor"
    total = profile["total"]
    assert total["matches"] == len(taylor)
    expected = sum(m.home_yellow_cards + m.away_yellow_cards for m in taylor) / len(taylor)  # type: ignore[operator]
    assert total["yellow"] == pytest.approx(expected, abs=0.01)
    assert total["home_yellow"] + total["away_yellow"] == pytest.approx(total["yellow"], abs=0.02)
    assert total["league_yellow"] == body["league_yellow"]
    assert len(profile["recent"]) == 5
    dates = [x["date"] for x in profile["recent"]]
    assert dates == sorted(dates, reverse=True)

    same = await client.get("/api/v1/referees/profile", params={"name": "A. Taylor"})
    assert same.json()["total"] == total
    missing = await client.get("/api/v1/referees/profile", params={"name": "Personne Inconnu"})
    assert missing.status_code == 404
    assert (await client.get("/api/v1/competitions/EPL/seasons/1990/referees")).status_code == 404
