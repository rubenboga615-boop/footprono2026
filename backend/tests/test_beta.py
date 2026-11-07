"""Mode bêta : partage volontaire, anonyme et temporaire ; Observatoire de la console."""

from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono.accounts import admin
from footprono.accounts import service as accounts
from footprono.accounts.models import BetaEvent, User
from footprono.beta import service
from footprono.bookmaker.models import Bet, BetSelection
from footprono.core.config import Settings
from footprono.football.models import DataSource, Match
from footprono.ingestion.service import IngestionRequest, run_ingestion

from .conftest import make_settings

Factory = async_sessionmaker[AsyncSession]
ADMIN = "+22997111111"
PLAYER = "+22997222222"
FIXTURES = Path(__file__).parent / "fixtures" / "football-data"


@pytest.fixture
def settings() -> Settings:
    return make_settings(beta_sharing=True)


async def _login(client: AsyncClient, db_factory: Factory, phone: str, role: str) -> dict:
    async with db_factory() as session:
        await accounts.register(
            session, make_settings(), phone=phone, password="12345678",
            display_name="Kofi Mensah", country="TG", adult=True,
        )  # fmt: skip
        if role == "admin":
            await admin.set_role(session, phone, "admin")
        await session.commit()
    path = "/api/v1/auth/console-login" if role == "admin" else "/api/v1/auth/login"
    r = await client.post(path, json={"phone": phone, "password": "12345678"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_paths_never_keep_identifiers() -> None:
    assert service.clean_path("/api/v1/matches/123/offer?x=1") == "/matches/{id}/offer"
    assert service.screen_of("/matches/{id}/offer") == "Cotes d'un match"
    assert service.screen_of("/montantes/{id}/suggestions") == "Suggestions de montante"
    assert service.screen_of("/smart-coupon") == "Coupon intelligent"


async def test_sharing_is_off_by_default_and_anonymous(
    client: AsyncClient, db_factory: Factory, tmp_path: Path
) -> None:
    await run_ingestion(
        db_factory,
        make_settings(raw_data_dir=tmp_path),
        [IngestionRequest(DataSource.FOOTBALL_DATA, ["EPL"], [2024], FIXTURES)],
    )
    player = await _login(client, db_factory, PLAYER, "user")
    me = (await client.get("/api/v1/me", headers=player)).json()
    assert me["beta_available"] is True
    assert me["beta_sharing"] is False
    assert me["beta_tester"] is None

    # Pas encore volontaire : rien n'est gardé.
    events = {"events": [{"kind": "timing", "path": "/api/v1/smart-coupon", "duration_ms": 900}]}
    r = await client.post("/api/v1/me/beta/events", json=events, headers=player)
    assert r.json() == {"kept": 0}

    on = await client.put("/api/v1/me/beta", json={"enabled": True}, headers=player)
    assert on.json() == {"enabled": True, "tester": 1}
    sent = {
        "events": [
            {"kind": "timing", "path": "/api/v1/smart-coupon", "duration_ms": 900},
            {"kind": "slow", "path": "/api/v1/smart-coupon", "duration_ms": 21000},
            {"kind": "error", "path": "/api/v1/matches/77/offer", "detail": "500"},
            {"kind": "action", "path": "coupon_compose", "at": "2026-01-01T10:00:00Z"},
            {"kind": "inconnu", "path": "/x"},
        ]
    }
    r = await client.post("/api/v1/me/beta/events", json=sent, headers=player)
    assert r.json() == {"kept": 4}

    async with db_factory() as session:
        user = await session.scalar(select(User).where(User.phone == PLAYER))
        match_id = await session.scalar(select(Match.id).limit(1))
        assert user is not None
        assert match_id is not None
        bet = Bet(
            user_id=user.id, kind="single", currency="XOF", stake=1000, total_odds=2,
            potential_payout=2000,
            status="settled", outcome="won", payout=2000,
        )  # fmt: skip
        session.add(bet)
        await session.flush()
        session.add(
            BetSelection(
                bet_id=bet.id, match_id=match_id, market="OU", line="2.5", selection="over",
                odds=2, bookmaker="1xBet", model_probability=0.55, result="win",
            )
        )  # fmt: skip
        await session.commit()

    head = await _login(client, db_factory, ADMIN, "admin")
    obs = (await client.get("/api/v1/admin/console/beta", headers=head)).json()
    assert obs["enabled"] is True
    assert obs["summary"]["testers"] == 1
    assert obs["summary"]["bets"] == 1
    assert obs["summary"]["over_20s_7_days"] == 1
    assert obs["summary"]["errors_7_days"] == 1
    row = obs["testers"][0]
    assert row["tester"] == 1
    assert row["win_rate"] == 1.0
    assert row["return"] == 1.0
    assert row["last_problem"]["screen"] in ("Coupon intelligent", "Cotes d'un match")
    assert obs["smart_coupons"] == {"composed": 1, "added": 0}
    assert obs["markets"][0]["selections"] == 1

    exported = await client.get("/api/v1/admin/console/beta/export", headers=head)
    text = exported.text
    # Jamais de données personnelles : ni nom, ni téléphone.
    assert PLAYER not in text
    assert "Kofi" not in text
    assert "+229" not in text
    assert len(exported.json()["events"]) == 4
    # Heure du téléphone gardée si plausible ; trop vieille (2026-01-01) : heure d'arrivée.
    assert not any(str(e["at"]).startswith("2026-01-01") for e in exported.json()["events"])

    # Le joueur éteint : ses événements sont effacés.
    off = await client.put("/api/v1/me/beta", json={"enabled": False}, headers=player)
    assert off.json() == {"enabled": False, "tester": None}
    async with db_factory() as session:
        assert await session.scalar(select(func.count()).select_from(BetaEvent)) == 0

    # Il revient : même numéro ; « Tout effacer » retire aussi les numéros.
    await client.put("/api/v1/me/beta", json={"enabled": True}, headers=player)
    await client.post("/api/v1/me/beta/events", json=sent, headers=player)
    erased = await client.delete("/api/v1/admin/console/beta", headers=head)
    assert erased.json() == {"events": 4, "testers": 1}
    me = (await client.get("/api/v1/me", headers=player)).json()
    assert me["beta_sharing"] is False
    assert me["beta_tester"] is None


async def test_nothing_is_collected_once_the_test_period_ends(
    client: AsyncClient, db_factory: Factory, settings: Settings
) -> None:
    player = await _login(client, db_factory, PLAYER, "user")
    await client.put("/api/v1/me/beta", json={"enabled": True}, headers=player)
    settings.beta_sharing = False
    me = (await client.get("/api/v1/me", headers=player)).json()
    assert me["beta_available"] is False
    assert me["beta_sharing"] is False
    refused = await client.put("/api/v1/me/beta", json={"enabled": True}, headers=player)
    assert refused.status_code == 409
    events = {"events": [{"kind": "timing", "path": "/api/v1/bets", "duration_ms": 50}]}
    r = await client.post("/api/v1/me/beta/events", json=events, headers=player)
    assert r.json() == {"kept": 0}
    # Éteindre reste toujours possible.
    off = await client.put("/api/v1/me/beta", json={"enabled": False}, headers=player)
    assert off.status_code == 200


async def test_player_routes_need_an_account_and_console_routes_an_admin(
    client: AsyncClient, db_factory: Factory
) -> None:
    assert (await client.put("/api/v1/me/beta", json={"enabled": True})).status_code == 401
    player = await _login(client, db_factory, PLAYER, "user")
    r = await client.get("/api/v1/admin/console/beta", headers=player)
    assert r.status_code in (401, 403)  # jeton de joueur : jamais la console


async def test_account_deletion_erases_the_tester_events(db_factory: Factory) -> None:
    from footprono.accounts.deletion import delete_account

    async with db_factory() as session:
        user = await accounts.register(
            session, make_settings(), phone=PLAYER, password="12345678",
            display_name="J", country="TG", adult=True,
        )  # fmt: skip
        await service.set_sharing(session, user, True)
        await service.record(session, user, [{"kind": "timing", "path": "/bets"}])
        await delete_account(session, user, "12345678")
        await session.commit()
        assert await session.scalar(select(func.count()).select_from(BetaEvent)) == 0


async def test_event_keeps_the_phone_time(db_factory: Factory) -> None:
    from datetime import UTC, datetime, timedelta

    async with db_factory() as session:
        user = await accounts.register(
            session, make_settings(), phone=PLAYER, password="12345678",
            display_name="J", country="TG", adult=True,
        )  # fmt: skip
        await service.set_sharing(session, user, True)
        tapped = datetime.now(UTC) - timedelta(minutes=3)
        await service.record(
            session, user, [{"kind": "action", "path": "coupon_add", "at": tapped}]
        )
        event = await session.scalar(select(BetaEvent))
        assert event is not None
        assert abs((event.created_at - tapped).total_seconds()) < 1
