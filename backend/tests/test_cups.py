"""Coupes d'Europe en base : équipes rattachées ou créées, score du temps réglementaire,
finale sur terrain neutre, jamais dans l'historique des championnats."""

from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono.engine.history import load_history
from footprono.football.models import Match, MatchStatus, Team, TeamAlias
from footprono.ingestion import cups
from footprono.ingestion.loader import sync_reference
from footprono.ingestion.reference import cup_season

Factory = async_sessionmaker[AsyncSession]


def _fx(fid: int, home: tuple[str, int], away: tuple[str, int], status: str = "NS",
        ft: tuple[int, int] | None = None, rnd: str = "League Stage - 1",
        day: str = "2026-10-21T19:00:00+00:00") -> dict[str, Any]:  # fmt: skip
    score = {"home": ft[0], "away": ft[1]} if ft else {"home": None, "away": None}
    return {
        "fixture": {"id": fid, "date": day, "status": {"short": status}},
        "league": {"id": 2, "season": 2026, "round": rnd},
        "teams": {
            "home": {"id": home[1], "name": home[0]},
            "away": {"id": away[1], "name": away[0]},
        },
        "score": {"fulltime": score, "halftime": {"home": 0, "away": 0} if ft else score},
    }


ARSENAL, QARABAG, PSG = ("Arsenal", 42), ("Qarabag", 556), ("Paris Saint Germain", 85)


async def test_cup_matches_loaded_and_kept_out_of_leagues(db_factory: Factory) -> None:
    async with db_factory() as session:
        await sync_reference(session)
        await cups.sync_cups(session)
        before = len(await load_history(session))
        stats = await cups.load_cup_fixtures(session, "UCL", [
            _fx(1, ARSENAL, QARABAG),
            # Prolongation : 1-1 après 90 minutes, 2-1 au bout ; le pari se règle sur 1-1.
            _fx(2, QARABAG, PSG, "AET", (1, 1), "Round of 16"),
            _fx(3, PSG, ARSENAL, "FT", (2, 0), "Final", "2027-05-29T19:00:00+00:00"),
        ])  # fmt: skip
        await session.commit()
        assert stats == {"inserted": 3, "updated": 0, "finished": 2}

        arsenal = await session.scalar(select(Team.id).where(Team.name == "Arsenal"))
        qarabag = await session.scalar(select(Team).where(Team.name == "Qarabag"))
        assert qarabag is not None
        assert qarabag.country == "Europe"  # équipe créée
        alias = await session.scalar(select(TeamAlias.team_id).where(TeamAlias.alias == "#42"))
        assert alias == arsenal  # équipe d'un de nos championnats : la même
        rows = {m.api_football_id: m for m in (await session.scalars(select(Match))).all()}
        assert rows[1].status is MatchStatus.SCHEDULED
        assert rows[1].home_team_id == arsenal
        assert (rows[2].home_goals, rows[2].away_goals, rows[2].api_status) == (1, 1, "AET")
        assert rows[3].neutral is True
        assert rows[2].neutral is False
        assert rows[1].round == "League Stage - 1"

        # Résultat arrivé : le match est mis à jour, pas recréé ; l'équipe renommée chez
        # API-Football reste la même (identifiant).
        again = await cups.load_cup_fixtures(
            session, "UCL", [_fx(1, ARSENAL, ("Qarabag FK", 556), "FT", (3, 0))]
        )
        await session.commit()
        assert again == {"inserted": 0, "updated": 1, "finished": 1}
        assert await session.scalar(select(func.count()).select_from(Match)) == 3
        assert await session.scalar(select(func.count()).where(Team.name == "Qarabag FK")) == 0

        assert len(await load_history(session)) == before  # aucun match de coupe


def test_cup_season() -> None:
    assert cup_season(date(2026, 11, 5)) == 2026
    assert cup_season(date(2027, 5, 29)) == 2026
    assert cup_season(date(2027, 6, 24)) == 2027  # premier tour de qualification
