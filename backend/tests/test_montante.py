"""Montante : plan, suggestions, paliers, avancement au règlement, encaissement."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono.bookmaker.montante import rolled_stake
from footprono.bookmaker.settlement import settle_bets
from footprono.football.models import Match, MatchStatus
from footprono.predictions.models import MatchPrediction, PredictionRun

from .test_bets import _login, _sel, world  # noqa: F401 (fixture partagée)

Factory = async_sessionmaker[AsyncSession]


def test_rolled_stake_secures_part_of_each_gain() -> None:
    assert rolled_stake(9_250, 0) == 9_250
    assert rolled_stake(9_250, 20) == 7_400
    assert rolled_stake(9_999, 33) == 6_699  # arrondi au franc inférieur


async def test_reference_plan_matches_the_validated_example(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
) -> None:
    # Exemple de docs/DESIGN.md : 6 paliers, départ 5 000 F CFA, cotes 1,60 → 1,90.
    odds = ["1.60", "1.70", "1.75", "1.80", "1.85", "1.90"]
    created = await client.post(
        "/api/v1/montantes",
        json={"start_stake": 5000, "steps": [{"odds_min": o, "odds_max": o} for o in odds]},
        headers=await _login(client),
    )
    assert created.status_code == 201, created.text
    plan = created.json()
    assert plan["final_payout_range"] == [150_582, 150_582]
    # Chance d'aller au bout selon les cotes (marge du bookmaker comprise) : 3,3 %.
    assert plan["chance_by_odds"] == 0.0332
    assert plan["steps"][0]["stake"] == 5000
    assert plan["steps"][1]["stake_range"] == [8000, 8000]
    too_short = await client.post(
        "/api/v1/montantes",
        json={"steps": [{"odds_min": "1.5", "odds_max": "1.6"}] * 3},
        headers=await _login(client),
    )
    assert too_short.status_code == 422


async def _predict(factory: Factory, match_ids: list[int]) -> None:
    async with factory() as session:
        run = PredictionRun(
            engine_version="test", as_of=date(2026, 1, 1), status="ok", parameters={}, report={}
        )
        session.add(run)
        await session.flush()
        for m in match_ids:
            session.add(
                MatchPrediction(
                    run_id=run.id, match_id=m, lambda_home=1.5, lambda_away=1.0, rho=0.0,
                    share_home=0.45, share_away=0.45, counts={}, context={},
                    markets={
                        "1X2||home": [0.60, 0, 0, 0],
                        "1X2||draw": [0.25, 0, 0, 0],
                        "1X2||away": [0.15, 0, 0, 0],
                        "OU|2.5|over": [0.50, 0, 0, 0],
                    },
                )
            )  # fmt: skip
        await session.commit()


async def _finish(factory: Factory, match_id: int, home: int, away: int) -> None:
    async with factory() as session:
        await session.execute(
            update(Match)
            .where(Match.id == match_id)
            .values(
                status=MatchStatus.FINISHED, home_goals=home, away_goals=away,
                result_source="api_football", api_status="FT",
            )
        )  # fmt: skip
        await session.commit()
        await settle_bets(session, datetime.now(UTC))


async def test_montante_end_to_end(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
    db_factory: Factory,
) -> None:
    await _predict(db_factory, [world["m1"], world["m2"]])
    headers = await _login(client)
    plan = (
        await client.post(
            "/api/v1/montantes",
            json={
                "start_stake": 5000,
                "secure_pct": 20,
                "steps": [{"odds_min": "1.80", "odds_max": "1.90"}] * 4,
            },
            headers=headers,
        )
    ).json()
    mid = plan["id"]

    proposals = (await client.get(f"/api/v1/montantes/{mid}/suggestions", headers=headers)).json()
    assert proposals["stake"] == 5000
    ranked = proposals["suggestions"]
    assert [s["model_probability"] for s in ranked] == [0.6, 0.6, 0.5]
    assert all(Decimal("1.80") <= Decimal(s["total_odds"]) <= Decimal("1.90") for s in ranked)
    assert ranked[0]["advised"] is True  # 60 % contre 1/1,85 = 54 %
    assert ranked[2]["advised"] is False  # 50 % contre 1/1,90 = 53 % : déconseillé

    # Palier 1 : victoire à domicile de m1 à 1,85, mise imposée (5 000).
    first = await client.post(
        f"/api/v1/montantes/{mid}/bet",
        json={"selections": [_sel(world["m1"], "1X2", "home")]},
        headers=headers,
    )
    assert first.status_code == 201, first.text
    assert (first.json()["stake"], first.json()["montante_step_id"] is not None) == (5000, True)
    again = await client.post(
        f"/api/v1/montantes/{mid}/bet",
        json={"selections": [_sel(world["m2"], "1X2", "home")]},
        headers=headers,
    )
    assert again.status_code == 400  # un seul pari en cours par palier
    await _finish(db_factory, world["m1"], 2, 0)

    plan = (await client.get(f"/api/v1/montantes/{mid}", headers=headers)).json()
    assert plan["current_step"] == 2
    assert plan["steps"][0]["payout"] == 9_250
    assert plan["steps"][1]["stake"] == 7_400  # 20 % du gain sécurisés
    assert plan["cashable"] == 9_250  # 1 850 sécurisés + 7 400 pas encore rejoués

    # Palier 2 : cote hors plage refusée, puis acceptée après avertissement.
    out = {"selections": [_sel(world["m2"], "1X2", "draw")]}
    refused = await client.post(f"/api/v1/montantes/{mid}/bet", json=out, headers=headers)
    assert refused.status_code == 400
    assert "hors de la plage" in refused.json()["error"]["message"]
    accepted = await client.post(
        f"/api/v1/montantes/{mid}/bet", json={**out, "accept_out_of_range": True}, headers=headers
    )
    assert accepted.status_code == 201
    busy = await client.post(f"/api/v1/montantes/{mid}/cash-out", headers=headers)
    assert busy.status_code == 400  # pari du palier en cours
    await _finish(db_factory, world["m2"], 1, 2)

    plan = (await client.get(f"/api/v1/montantes/{mid}", headers=headers)).json()
    assert plan["status"] == "lost"
    assert plan["steps"][1]["out_of_range"] is True
    assert plan["cashable"] == 1_850  # seule la part sécurisée reste acquise
