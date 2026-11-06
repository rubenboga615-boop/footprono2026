"""Sélections nationales en base : terrain neutre des phases finales, amicaux filtrés,
équipes jamais confondues avec un club, hors des modèles et des listes des championnats."""

from datetime import date
from typing import Any

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono.engine.history import load_history
from footprono.football.models import Match, Team
from footprono.ingestion import nations
from footprono.ingestion.loader import sync_reference
from footprono.ingestion.quality import run_quality_checks
from footprono.ingestion.reference import nation_neutral

Factory = async_sessionmaker[AsyncSession]

BRAZIL, ARGENTINA = ("Brazil", 6), ("Argentina", 26)
IVORY, NIGERIA = ("Ivory Coast", 1501), ("Nigeria", 19)
CLUB = ("Pakhtakor", 9999)
YOUTH = ("Brazil U20", 8888)


def _fx(fid: int, home: tuple[str, int], away: tuple[str, int], when: str, season: int,
        city: str | None = None, status: str = "FT") -> dict[str, Any]:  # fmt: skip
    return {
        "fixture": {"id": fid, "date": when, "status": {"short": status},
                    "venue": {"name": None, "city": city}},
        "league": {"id": 1, "season": season, "round": "Group Stage - 1"},
        "teams": {"home": {"id": home[1], "name": home[0]},
                  "away": {"id": away[1], "name": away[0]}},
        "score": {"fulltime": {"home": 2, "away": 1}, "halftime": {"home": 1, "away": 0}},
    }  # fmt: skip


def test_neutral_venue_in_final_phases_only() -> None:
    # CAN 2023 en Côte d'Ivoire : le pays hôte reçoit chez lui, les autres sur terrain neutre.
    assert not nation_neutral("CAN", 2023, date(2024, 1, 13), "Ivory Coast", "Abidjan")
    assert nation_neutral("CAN", 2023, date(2024, 1, 14), "Nigeria", "Abidjan")
    # Éliminatoires (hors des dates de la phase finale) : l'équipe qui reçoit est chez elle.
    assert not nation_neutral("CAN", 2019, date(2018, 9, 8), "Nigeria", None)
    assert not nation_neutral("WCQ_AFR", 2023, date(2025, 3, 21), "Ivory Coast", "Abidjan")
    # Euro 2020 dans onze pays : l'Allemagne chez elle à Munich, pas à Londres.
    assert not nation_neutral("EURO", 2020, date(2021, 6, 15), "Germany", "München")
    assert nation_neutral("EURO", 2020, date(2021, 6, 29), "Germany", "London")
    # Coupe du Monde 2026 : les États-Unis neutres à Toronto.
    assert nation_neutral("WC", 2026, date(2026, 6, 20), "USA", "Toronto")
    assert not nation_neutral("WC", 2026, date(2026, 6, 12), "USA", "Inglewood")


async def test_nations_loaded_apart_from_clubs(db_factory: Factory, client: AsyncClient) -> None:
    async with db_factory() as session:
        await sync_reference(session)
        await nations.sync_nations(session)
        session.add(Team(name="Brazil", country="Brazil"))  # club homonyme
        await session.commit()
        before = len(await load_history(session))

        wc = await nations.load_nation_fixtures(session, "WC", [
            _fx(1, BRAZIL, ARGENTINA, "2022-11-24T19:00:00+00:00", 2022, "Doha"),
            _fx(2, IVORY, NIGERIA, "2022-11-25T19:00:00+00:00", 2022, "Doha"),
        ])  # fmt: skip
        friendlies = await nations.load_nation_fixtures(session, "AMICAL", [
            _fx(3, BRAZIL, NIGERIA, "2023-03-25T19:00:00+00:00", 2023, "Rio de Janeiro"),
            _fx(4, BRAZIL, CLUB, "2023-03-28T19:00:00+00:00", 2023),  # club : écarté
            _fx(5, YOUTH, NIGERIA, "2023-03-29T19:00:00+00:00", 2023),  # jeunes : écarté
        ])  # fmt: skip
        await session.commit()
        assert wc == {"inserted": 2, "updated": 0, "finished": 2, "skipped": 0}
        assert friendlies["inserted"] == 1
        assert friendlies["skipped"] == 2

        rows = {m.api_football_id: m for m in (await session.scalars(select(Match))).all()}
        assert rows[1].neutral is True  # Coupe du Monde 2022 au Qatar
        assert rows[3].neutral is False  # amical : le Brésil reçoit
        club = await session.scalar(select(Team).where(Team.name == "Brazil"))
        selection = await session.scalar(select(Team).where(Team.name == "Brazil (Sélections)"))
        assert club is not None
        assert selection is not None
        assert rows[1].home_team_id == selection.id  # jamais le club homonyme
        assert await session.scalar(select(func.count()).where(Team.name == "Pakhtakor")) == 0

        assert len(await load_history(session)) == before  # hors des championnats
        quality = await run_quality_checks(session, today=date(2026, 11, 6))
        assert not [f for f in quality["findings"] if f["competition"] in ("WC", "AMICAL")]

    for params in ({}, {"cups": "true"}):
        codes = {
            c["code"] for c in (await client.get("/api/v1/competitions", params=params)).json()
        }
        assert "WC" not in codes
        assert "AMICAL" not in codes


async def test_update_without_key_makes_no_request(db_factory: Factory) -> None:
    from .conftest import make_settings

    async with db_factory() as session:
        report = await nations.update_nations(session, make_settings())
    assert report["status"] == "unavailable"
