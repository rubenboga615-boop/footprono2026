"""Comparaison des moteurs (maquettes K1-K3) : le moteur 2 est servi à côté du moteur 1,
jamais à sa place ; réglage du compte, fiche de match, Coupon intelligent."""

from datetime import timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono.bookmaker import service, smart_coupon
from footprono.predictions import calibration

from .conftest import make_premium
from .test_bets import NOW, _login, quote, world  # noqa: F401 (fixture partagée)
from .test_montante import _predict
from .test_smart_coupon import DAY, KICKOFF, MORNING, _evening, _frozen_clock  # noqa: F401

Factory = async_sessionmaker[AsyncSession]


async def _reference(factory: Factory, match_id: int, age: timedelta = timedelta(hours=1)) -> None:
    """Cotes de référence (Pinnacle) : favori à domicile, plus de 2,5 buts un peu probable."""
    seen = NOW - age
    async with factory() as session:
        session.add_all(
            [
                quote(match_id, "Pinnacle", "Match Winner", "Home", "1.45", seen),
                quote(match_id, "Pinnacle", "Match Winner", "Draw", "4.60", seen),
                quote(match_id, "Pinnacle", "Match Winner", "Away", "7.50", seen),
                quote(match_id, "Pinnacle", "Goals Over/Under", "Over 2.5", "1.80", seen),
                quote(match_id, "Pinnacle", "Goals Over/Under", "Under 2.5", "2.05", seen),
            ]
        )
        await session.commit()


async def test_engine2_is_calibrated_and_engine1_is_unchanged(
    world: dict[str, Any],  # noqa: F811
    db_factory: Factory,
) -> None:
    m1, m2 = world["m1"], world["m2"]
    await _predict(db_factory, [m1, m2])  # moteur 1 : domicile 60 %
    await _reference(db_factory, m1)
    async with db_factory() as session:
        quotes = await calibration.reference_quotes(session, [m1, m2], NOW)
        engine1 = await service.models_probabilities(session, [m1, m2])
        engine2 = await service.engine2_probabilities(session, [m1, m2], NOW)
    assert set(quotes) == {m1}
    # Moteur 1 : rien ne change, même avec la cote de référence.
    assert engine1[m1]["1X2||home"] == 0.60
    assert service.CALIBRATED_KEY not in engine1[m1]
    # Moteur 2 : m1 calé (favori vers 66 %), m2 sans référence = moteur 1.
    assert service.CALIBRATED_KEY in engine2[m1]
    assert 0.63 < engine2[m1]["1X2||home"] < 0.69
    assert service.is_priced(engine2[m1], "1X2")
    assert service.CALIBRATED_KEY not in engine2[m2]
    assert engine2[m2]["1X2||home"] == 0.60
    assert set(engine2[m1]) - {service.CALIBRATED_KEY} == set(engine1[m1])


async def test_stale_reference_is_ignored(
    world: dict[str, Any],  # noqa: F811
    db_factory: Factory,
) -> None:
    m1 = world["m1"]
    await _predict(db_factory, [m1])
    await _reference(db_factory, m1)
    service.clear_window_cache()
    async with db_factory() as session:
        later = NOW + calibration.REFERENCE_MAX_AGE
        probs = (await service.engine2_probabilities(session, [m1], later))[m1]
    assert service.CALIBRATED_KEY not in probs
    assert probs["1X2||home"] == 0.60


async def test_match_offer_shows_engine2_only_in_comparison_mode(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
    db_factory: Factory,
) -> None:
    m1 = world["m1"]
    await _predict(db_factory, [m1])
    await _reference(db_factory, m1)
    headers = await _login(client)
    me = (await client.get("/api/v1/me", headers=headers)).json()
    assert me["compare_engines"] is False

    def home(offers: list[dict[str, Any]]) -> dict[str, Any]:
        return next(o for o in offers if (o["market"], o["selection"]) == ("1X2", "home"))

    off = home((await client.get(f"/api/v1/matches/{m1}/offer", headers=headers)).json())
    assert off["model_probability"] == 0.60
    assert off["engine2_probability"] is None
    assert off["engine2_calibrated"] is None

    r = await client.put("/api/v1/me/preferences", json={"compare_engines": True}, headers=headers)
    assert r.status_code == 204
    assert (await client.get("/api/v1/me", headers=headers)).json()["compare_engines"] is True
    on = home((await client.get(f"/api/v1/matches/{m1}/offer", headers=headers)).json())
    assert on["model_probability"] == 0.60  # moteur 1 inchangé
    assert 0.63 < on["engine2_probability"] < 0.69
    assert on["engine2_calibrated"] is True
    # Sans connexion : jamais le moteur 2.
    anon = home((await client.get(f"/api/v1/matches/{m1}/offer")).json())
    assert anon["engine2_probability"] is None


async def test_smart_coupon_engine2(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
    db_factory: Factory,
) -> None:
    m1, m2 = world["m1"], world["m2"]
    await _predict(db_factory, [m1, m2])
    await _evening(db_factory, [m1, m2])
    await _reference(db_factory, m1)
    headers = await _login(client)
    await make_premium(db_factory, "+22997111111")
    params: dict[str, Any] = {"profile": "equilibre", "period": "tomorrow", "size": 2}

    refused = await client.get(
        "/api/v1/smart-coupon", params={**params, "engine": 2}, headers=headers
    )
    assert refused.status_code == 400
    assert "Comparer les deux moteurs" in refused.text

    one = (await client.get("/api/v1/smart-coupon", params=params, headers=headers)).json()
    await client.put("/api/v1/me/preferences", json={"compare_engines": True}, headers=headers)
    one_again = (await client.get("/api/v1/smart-coupon", params=params, headers=headers)).json()
    two = (
        await client.get("/api/v1/smart-coupon", params={**params, "engine": 2}, headers=headers)
    ).json()

    # Moteur 1 : le même coupon qu'avant (domicile à 60 % dans les deux matchs, 3,42).
    assert one["engine"] == 1
    assert one["coupon"]["total_odds"] == "3.42"
    assert one_again["coupon"]["selections"] == one["coupon"]["selections"]
    assert [s["price_tier"] for s in one["coupon"]["selections"]] == [None, None]
    # Moteur 2 : m2 non calé (neutre) d'abord, puis m1 calé (domicile 1,85 bien au-dessus
    # de la cote juste ≈ 1,52 : cote suspecte, prise faute d'autre choix dans la tranche).
    assert two["engine"] == 2
    sel = {s["match_id"]: s for s in two["coupon"]["selections"]}
    assert set(sel) == {m1, m2}
    assert sel[m2]["price_tier"] is None
    assert sel[m1]["price_tier"] == "suspect"
    assert sel[m1]["price"] == pytest.approx(sel[m1]["model_probability"] * 1.85, abs=0.002)
    assert two["coupon"]["probability"] > one["coupon"]["probability"]


async def test_grosse_cote_stays_engine1(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
    db_factory: Factory,
) -> None:
    headers = await _login(client)
    await make_premium(db_factory, "+22997111111")
    await client.put("/api/v1/me/preferences", json={"compare_engines": True}, headers=headers)
    r = await client.get(
        "/api/v1/smart-coupon",
        params={"profile": "grosse", "target_odds": "5", "period": "tomorrow", "engine": 2},
        headers=headers,
    )
    assert r.status_code == 400


async def test_montante_suggestions_of_both_engines_and_the_engine_is_kept(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
    db_factory: Factory,
) -> None:
    m1, m2 = world["m1"], world["m2"]
    await _predict(db_factory, [m1, m2])
    await _reference(db_factory, m1)
    headers = await _login(client)
    await make_premium(db_factory, "+22997111111")
    mid = (
        await client.post(
            "/api/v1/montantes",
            json={"start_stake": 5000, "steps": [{"odds_min": "1.80", "odds_max": "1.90"}] * 4},
            headers=headers,
        )
    ).json()["id"]
    url = f"/api/v1/montantes/{mid}/suggestions"
    refused = await client.get(url, params={"engine": 2}, headers=headers)
    assert refused.status_code == 400
    await client.put("/api/v1/me/preferences", json={"compare_engines": True}, headers=headers)

    one = (await client.get(url, headers=headers)).json()
    two = (await client.get(url, params={"engine": 2}, headers=headers)).json()
    assert (one["engine"], two["engine"]) == (1, 2)
    # Moteur 1 : même classement que sans comparaison (cote la plus basse, probabilités
    # du moteur 1, jamais de prix).
    assert [s["model_probability"] for s in one["suggestions"]] == [0.6, 0.6, 0.5]
    assert {sel["price_tier"] for s in one["suggestions"] for sel in s["selections"]} == {None}
    # Moteur 2 : m1 calé (domicile 1,85 bien au-dessus de la cote juste : suspect), donc
    # proposé après les paris neutres.
    first = two["suggestions"][0]["selections"]
    assert all(sel["price_tier"] != "suspect" for sel in first)
    tiers = [
        max((sel["price_tier"] or "neutral") == "suspect" for sel in s["selections"])
        for s in two["suggestions"]
    ]
    assert tiers == sorted(tiers)

    # Le palier joué garde le nom du moteur qui l'a proposé.
    sel = first[0]
    bet = await client.post(
        f"/api/v1/montantes/{mid}/bet",
        json={
            "selections": [
                {k: sel[k] for k in ("match_id", "market", "selection", "odds")}
                | {"line": sel["line"] or ""}
            ],
            "from_suggestion": True,
            "engine": 2,
        },
        headers=headers,
    )
    assert bet.status_code == 201, bet.text
    plan = (await client.get(f"/api/v1/montantes/{mid}", headers=headers)).json()
    assert plan["steps"][0]["engine"] == 2
    assert plan["steps"][1]["engine"] is None


async def test_daily_coupons_of_engine2_are_kept_apart(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
    db_factory: Factory,
) -> None:
    m1, m2 = world["m1"], world["m2"]
    await _predict(db_factory, [m1, m2])
    await _evening(db_factory, [m1, m2])
    await _reference(db_factory, m1)
    async with db_factory() as session:
        one = await smart_coupon.create_daily(session, MORNING)
        two = await smart_coupon.create_daily(session, MORNING, engine=2)
        again = await smart_coupon.create_daily(session, MORNING, engine=2)
    # Chaque moteur ses coupons : le moteur 2 reprend m1 et m2 sans gêner le moteur 1.
    assert one["equilibre"].startswith("2 sélection(s)")
    assert two["equilibre"].startswith("2 sélection(s)")
    assert again["equilibre"] == "déjà créé"
    async with db_factory() as session:
        day1 = await smart_coupon.day_coupons(session, DAY, MORNING)
        day2 = await smart_coupon.day_coupons(session, DAY, MORNING, engine=2)
        history = await smart_coupon.history(session)
    assert [c["profile"] for c in day1["coupons"]] == ["equilibre"]
    assert [c["profile"] for c in day2["coupons"]] == ["equilibre"]
    assert day1["coupons"][0]["id"] != day2["coupons"][0]["id"]
    # L'historique public reste celui du moteur 1.
    assert [c["id"] for c in history["coupons"]] == [day1["coupons"][0]["id"]]

    headers = await _login(client)
    params = {"day": str(DAY), "engine": 2}
    refused = await client.get("/api/v1/smart-coupons/day", params=params, headers=headers)
    assert refused.status_code == 400
    await client.put("/api/v1/me/preferences", json={"compare_engines": True}, headers=headers)
    got = (await client.get("/api/v1/smart-coupons/day", params=params, headers=headers)).json()
    assert got["engine"] == 2
    assert [c["id"] for c in got["coupons"]] == [day2["coupons"][0]["id"]]


async def test_engines_reliability_records_settles_and_judges(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
    db_factory: Factory,
) -> None:
    from sqlalchemy import select, update

    from footprono.bookmaker import engine_compare
    from footprono.bookmaker.smart_models import EngineMatchChances, EngineProposal
    from footprono.football.models import Match, MatchStatus

    m1, m2 = world["m1"], world["m2"]
    await _predict(db_factory, [m1, m2])
    await _evening(db_factory, [m1, m2])
    # Cote de référence relevée 2 heures avant le match : récente au moment du relevé des
    # chances (sinon, selon l'heure du test, plus de 36 heures avant le soir de demain).
    await _reference(db_factory, m1, NOW - (KICKOFF - timedelta(hours=2)))
    headers = await _login(client)
    await make_premium(db_factory, "+22997111111")
    assert (await client.get("/api/v1/reliability/engines", headers=headers)).status_code == 400
    await client.put("/api/v1/me/preferences", json={"compare_engines": True}, headers=headers)

    # Chaque proposition de chaque moteur est enregistrée, une fois par jour.
    params: dict[str, Any] = {"profile": "equilibre", "period": "tomorrow", "size": 2}
    for engine in (1, 2, 1):
        r = await client.get(
            "/api/v1/smart-coupon", params={**params, "engine": engine}, headers=headers
        )
        assert r.status_code == 200, r.text
    # Chances des deux moteurs relevées avant les matchs.
    async with db_factory() as session:
        recorded = await engine_compare.record_chances(session, KICKOFF - timedelta(hours=1))
        proposals = (await session.scalars(select(EngineProposal))).all()
    assert recorded == 2
    assert sorted(p.engine for p in proposals) == [1, 2]
    assert all(p.source == "coupon" for p in proposals)

    # Résultats : domicile 2-0 dans les deux matchs ; propositions réglées à 1 000 F.
    async with db_factory() as session:
        await session.execute(
            update(Match)
            .where(Match.id.in_([m1, m2]))
            .values(status=MatchStatus.FINISHED, home_goals=2, away_goals=0, api_status="FT",
                    result_source="api_football")
        )  # fmt: skip
        await session.commit()
        assert await engine_compare.settle_proposals(session) == 2
        chances = {c.match_id: c for c in (await session.scalars(select(EngineMatchChances))).all()}
    assert chances[m1].calibrated
    assert not chances[m2].calibrated
    assert chances[m2].engine1 == chances[m2].engine2  # non calé : mêmes chances

    body = (await client.get("/api/v1/reliability/engines", headers=headers)).json()
    assert body["matches"] == 2
    assert body["calibrated"] == 1
    # Moteur 2 plus confiant sur le favori de m1, qui a gagné : log loss plus basse.
    assert body["log_loss"]["2"] < body["log_loss"]["1"]
    coupon = next(m for m in body["money"] if m["source"] == "coupon")
    one = coupon["engines"]["1"]
    assert (one["settled"], one["won"]) == (1, 1)
    assert one["profit"] == 2422  # 1 000 F à 1,85 fois 1,85 (3,4225) : 3 422 rendus
    assert body["enough"] is False  # jamais de verdict avec 2 matchs


async def test_console_creates_the_daily_coupons_of_both_engines(
    world: dict[str, Any],  # noqa: F811
    db_factory: Factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from footprono.console import actions
    from footprono.console.jobs import JobContext

    from .conftest import make_settings

    m1, m2 = world["m1"], world["m2"]
    await _predict(db_factory, [m1, m2])
    await _evening(db_factory, [m1, m2])
    real = smart_coupon.create_daily

    async def at_morning(session: Any, now: Any = None, engine: int = 1) -> Any:
        return await real(session, MORNING, engine=engine)

    monkeypatch.setattr(smart_coupon, "create_daily", at_morning)
    ctx = JobContext(db_factory, make_settings(), 0)
    summary = await actions.daily_coupons(ctx, {})
    assert "equilibre : 2 sélection(s)" in summary
    assert "moteur 2, equilibre : 2 sélection(s)" in summary
