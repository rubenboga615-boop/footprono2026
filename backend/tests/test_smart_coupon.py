"""Coupon intelligent : génération, coupons du jour, règlement, historique, marchés retirés."""

from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono.bookmaker import smart_coupon
from footprono.engine.markets import offered
from footprono.football.models import Match, MatchStatus

from .test_bets import NOW, _login, quote, world  # noqa: F401 (fixture partagée)
from .test_montante import _predict

Factory = async_sessionmaker[AsyncSession]
DAY = (NOW + timedelta(days=1)).date()
KICKOFF = datetime(DAY.year, DAY.month, DAY.day, 20, tzinfo=UTC)
MORNING = datetime(DAY.year, DAY.month, DAY.day, 8, 5, tzinfo=UTC)


async def _evening(factory: Factory, ids: list[int]) -> None:
    async with factory() as session:
        await session.execute(update(Match).where(Match.id.in_(ids)).values(kickoff_at=KICKOFF))
        await session.commit()


async def _result(factory: Factory, match_id: int, home: int, away: int) -> dict[str, int]:
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
        return await smart_coupon.settle_pending(session, KICKOFF + timedelta(hours=3))


def test_period_windows() -> None:
    friday = datetime(2026, 10, 2, 10, tzinfo=UTC)
    start, end = smart_coupon.period_window("today", friday)
    assert (start, end) == (friday + timedelta(minutes=15), datetime(2026, 10, 3, tzinfo=UTC))
    assert smart_coupon.period_window("weekend", friday) == (
        datetime(2026, 10, 3, tzinfo=UTC),
        datetime(2026, 10, 5, tzinfo=UTC),
    )
    sunday = datetime(2026, 10, 4, 12, tzinfo=UTC)
    assert smart_coupon.period_window("weekend", sunday)[1] == datetime(2026, 10, 5, tzinfo=UTC)
    assert smart_coupon.period_window("week", friday)[1] == datetime(2026, 10, 9, tzinfo=UTC)
    assert smart_coupon.french_day(friday) == "vendredi 2 octobre"


def test_automatic_markets() -> None:
    from footprono.bookmaker.rules import automatic

    # Handicap asiatique : moins bien que pile ou face à la ligne du bookmaker.
    assert not automatic("AH")
    assert not automatic("CORNERS_AH")
    assert not automatic("CARDS_OU")
    assert automatic("OU")
    assert automatic("EH")


def test_sure_profile_aims_at_the_middle() -> None:
    from types import SimpleNamespace

    def pick(p: float) -> smart_coupon.Pick:
        return smart_coupon.Pick(SimpleNamespace(), "A", "B", "EPL", SimpleNamespace(), p)  # type: ignore[arg-type]

    inside = [pick(0.91), pick(0.84), pick(0.78)]
    # « Sûr » : la plus proche de 83,5 % (cote plus utile), pas la plus probable.
    assert smart_coupon.choose(smart_coupon.PROFILES["sur"], inside).probability == 0.84
    # Les autres profils gardent la plus probable de leur tranche.
    assert smart_coupon.choose(smart_coupon.PROFILES["equilibre"], inside).probability == 0.91


def test_withdrawn_markets() -> None:
    assert not offered("ODD_EVEN||odd")
    assert not offered("HT_BTTS||yes")
    assert not offered("HIGHEST_HALF||first")
    assert offered("BTTS||yes")
    assert offered("HT_OU|0.5|over")


async def test_smart_coupon_api(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
    db_factory: Factory,
) -> None:
    m1, m2 = world["m1"], world["m2"]
    await _predict(db_factory, [m1, m2])
    await _evening(db_factory, [m1, m2])
    headers = await _login(client)  # essai Premium à l'inscription

    r = await client.get(
        "/api/v1/smart-coupon",
        params={"profile": "equilibre", "period": "tomorrow", "size": 2},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    coupon = body["coupon"]
    # Victoire à domicile (60 %, cote 1,85) dans chaque match ; jamais deux sélections d'un match.
    picked = [(s["match_id"], s["market"], s["selection"]) for s in coupon["selections"]]
    assert sorted(picked) == sorted([(m1, "1X2", "home"), (m2, "1X2", "home")])
    assert coupon["total_odds"] == "3.42"
    assert coupon["probability"] == 0.36
    assert all(s["reasons"] for s in coupon["selections"])
    assert body["message"] is None

    # Aucune sélection « sûre » (75 % et plus) : dit clairement, rien d'inventé.
    sure = (
        await client.get(
            "/api/v1/smart-coupon", params={"profile": "sur", "period": "tomorrow"}, headers=headers
        )
    ).json()
    assert sure["coupon"] is None
    assert "Seulement 0 match" in sure["message"]

    # Rien aujourd'hui (matchs demain soir) : la date des prochains matchs est donnée.
    today = (
        await client.get(
            "/api/v1/smart-coupon", params={"profile": "equilibre", "period": "today"},
            headers=headers,
        )
    ).json()  # fmt: skip
    if NOW.date() < DAY:
        assert today["coupon"] is None
        assert "Prochains matchs à partir du" in today["message"]
    # « Prochaine journée » : trouve toujours les prochains matchs, même après une trêve.
    nxt = (
        await client.get(
            "/api/v1/smart-coupon", params={"profile": "equilibre", "period": "next", "size": 2},
            headers=headers,
        )
    ).json()  # fmt: skip
    assert len(nxt["coupon"]["selections"]) == 2

    bad = await client.get("/api/v1/smart-coupon", params={"size": 13}, headers=headers)
    assert bad.status_code == 400
    assert (await client.get("/api/v1/smart-coupon")).status_code == 401


async def test_daily_coupons_settled_and_public(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
    db_factory: Factory,
) -> None:
    m1, m2 = world["m1"], world["m2"]
    await _predict(db_factory, [m1, m2])
    await _evening(db_factory, [m1, m2])
    async with db_factory() as session:
        created = await smart_coupon.create_daily(session, MORNING)
        assert created["sur"] == "aucune sélection"
        assert created["equilibre"].startswith("2 sélection(s)")
        again = await smart_coupon.create_daily(session, MORNING)
        assert again["equilibre"] == "déjà créé"

    # m1 1-0 : « audacieux » (+2,5 buts) perdu sans attendre m2 ; « équilibré » en cours.
    assert await _result(db_factory, m1, 1, 0) == {"won": 0, "lost": 1, "partial": 0, "void": 0}
    # m2 2-1 : « équilibré » gagné.
    assert await _result(db_factory, m2, 2, 1) == {"won": 1, "lost": 0, "partial": 0, "void": 0}

    public = (await client.get("/api/v1/smart-coupons/history")).json()
    status = {c["profile"]: c["status"] for c in public["coupons"]}
    assert status == {"equilibre": "won", "audacieux": "lost"}
    lost = next(c for c in public["coupons"] if c["profile"] == "audacieux")
    assert {s["match_id"]: s["result"] for s in lost["selections"]} == {m1: "loss", m2: "pending"}
    assert public["stats"]["equilibre"] == {
        "label": "Équilibré", "settled": 1, "won": 1, "announced": 0.36, "observed": 1.0,
    }  # fmt: skip
    assert public["stats"]["sur"]["settled"] == 0


async def test_withdrawn_market_not_offered(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
    db_factory: Factory,
) -> None:
    async with db_factory() as session:
        session.add(
            quote(world["m1"], "1xBet", "Odd/Even", "Odd", "1.90", NOW - timedelta(hours=1))
        )
        await session.commit()
    offer = (await client.get(f"/api/v1/matches/{world['m1']}/offer")).json()
    assert {o["market"] for o in offer} >= {"1X2"}
    assert "ODD_EVEN" not in {o["market"] for o in offer}


def _fake(match_id: int, odds: str, p: float) -> smart_coupon.Pick:
    from decimal import Decimal
    from types import SimpleNamespace

    offer = SimpleNamespace(odds=Decimal(odds), quote_id=match_id)
    match = SimpleNamespace(id=match_id)
    return smart_coupon.Pick(match, "A", "B", "EPL", offer, p)  # type: ignore[arg-type]


def test_target_coupon_adds_most_probable_until_target() -> None:
    from decimal import Decimal

    # Déjà classées du plus probable au moins probable (best_angles) : jamais réordonnées
    # selon la cote, pour ne pas choisir là où le moteur contredit le bookmaker.
    ranked = [_fake(1, "1.30", 0.80), _fake(2, "1.50", 0.66), _fake(3, "1.80", 0.55),
              _fake(4, "2.10", 0.47)]  # fmt: skip
    picks = smart_coupon.target_coupon(ranked, Decimal("3.5"), max_size=12)
    assert [pk.match.id for pk in picks] == [1, 2, 3]  # 1,30 x 1,50 x 1,80 = 3,51
    # Jamais une sélection prise « parce que sa cote suffit » : ordre des probabilités.
    last = smart_coupon.target_coupon(ranked, Decimal("2.5"), max_size=12)
    assert [pk.match.id for pk in last] == [1, 2, 3]
    assert smart_coupon.target_coupon(ranked, Decimal("3.5"), max_size=2) == []
    assert smart_coupon.target_coupon(ranked, Decimal("100"), max_size=12) == []


async def test_grosse_cote_filters_and_periods(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
    db_factory: Factory,
) -> None:
    m1, m2 = world["m1"], world["m2"]
    await _predict(db_factory, [m1, m2])
    await _evening(db_factory, [m1, m2])
    headers = await _login(client)

    async def gen(**params: Any) -> dict[str, Any]:
        r = await client.get("/api/v1/smart-coupon", params=params, headers=headers)
        assert r.status_code == 200, r.text
        return r.json()

    big = await gen(profile="grosse", period="tomorrow", target_odds="3", size=12)
    coupon = big["coupon"]
    assert float(coupon["total_odds"]) >= 3
    assert coupon["one_in"] == round(1 / coupon["probability"])
    assert len({s["match_id"] for s in coupon["selections"]}) == len(coupon["selections"])
    assert big["profile_label"] == "Grosse cote"

    impossible = await gen(profile="grosse", period="tomorrow", target_odds="500", size=12)
    assert impossible["coupon"] is None
    assert "Impossible d'atteindre une cote de 500" in impossible["message"]
    no_target = await client.get(
        "/api/v1/smart-coupon", params={"profile": "grosse"}, headers=headers
    )
    assert no_target.status_code == 400

    one_day = await gen(profile="equilibre", period="day", day=DAY.isoformat(), size=2)
    assert len(one_day["coupon"]["selections"]) == 2
    assert one_day["period_label"] == smart_coupon.french_day(KICKOFF)
    span = await gen(profile="equilibre", period="range", date_from=DAY.isoformat(),
                     date_to=(DAY + timedelta(days=2)).isoformat(), size=2)  # fmt: skip
    assert len(span["coupon"]["selections"]) == 2

    without_m1 = await gen(profile="equilibre", period="tomorrow", size=2, exclude_matches=[m1])
    assert [s["match_id"] for s in without_m1["coupon"]["selections"]] == [m2]
    team = without_m1["coupon"]["selections"][0]["home_team_id"]
    no_team = await gen(profile="equilibre", period="tomorrow", size=2, exclude_teams=[team])
    assert m2 not in [s["match_id"] for s in no_team["coupon"]["selections"]]
    late = await gen(profile="equilibre", period="tomorrow", size=2, after_hour=21)
    assert late["coupon"] is None  # matchs à 20 h : avant l'heure demandée

    assert (await client.get("/api/v1/smart-coupon", params={"period": "day"},
                             headers=headers)).status_code == 400  # fmt: skip


async def test_match_picks_free_and_premium(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
    db_factory: Factory,
) -> None:
    m1 = world["m1"]
    await _predict(db_factory, [m1])
    free = (await client.get(f"/api/v1/matches/{m1}/picks")).json()["picks"]
    assert free["sur"]["locked"] is False
    assert free["equilibre"]["locked"] is True
    assert free["equilibre"]["selection"] is None
    headers = await _login(client)
    full = (await client.get(f"/api/v1/matches/{m1}/picks", headers=headers)).json()["picks"]
    sel = full["equilibre"]["selection"]
    assert (sel["market"], sel["selection"]) == ("1X2", "home")
    assert full["equilibre"]["label"] == "Équilibré"


async def test_day_coupons_live_state_and_booking_codes(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
    db_factory: Factory,
) -> None:
    """Coupons d'un jour : état en direct de chaque sélection ; code de réservation saisi
    par l'administrateur seulement, nettoyé, vérifié, puis visible de tous."""
    from footprono.accounts import admin

    m1, m2 = world["m1"], world["m2"]
    await _predict(db_factory, [m1, m2])
    await _evening(db_factory, [m1, m2])
    async with db_factory() as session:
        await smart_coupon.create_daily(session, MORNING)
        await session.execute(
            update(Match).where(Match.id == m1).values(
                api_status="2H", live_minute=58, live_home_goals=1, live_away_goals=0,
            )
        )  # fmt: skip
        await session.commit()

    day = (await client.get("/api/v1/smart-coupons/day", params={"day": str(DAY)})).json()
    coupon = next(c for c in day["coupons"] if c["profile"] == "equilibre")
    assert coupon["display_status"] == "live"
    assert coupon["validated"] == 0
    assert coupon["booking_codes"] == []
    states = {s["match_id"]: s for s in coupon["selections"]}
    assert (states[m1]["state"], states[m1]["minute"], states[m1]["score"]) == ("live", 58, [1, 0])
    assert states[m2]["state"] == "upcoming"
    assert set(day["summary"]) == {"yesterday", "last_30_days"}

    url = f"/api/v1/admin/smart-coupons/{coupon['id']}/booking-code"
    player = await _login(client)
    assert (await client.put(url, json={"code": "7HQ2K"}, headers=player)).status_code == 401
    async with db_factory() as session:
        await admin.set_role(session, "+22997111111", "admin")
        await session.commit()
    console = await client.post(
        "/api/v1/auth/console-login", json={"phone": "+22997111111", "password": "12345678"}
    )
    headers = {"Authorization": f"Bearer {console.json()['access_token']}"}
    saved = await client.put(url, json={"bookmaker": "1xbet", "code": " 7hq 2k "}, headers=headers)
    assert saved.status_code == 200
    bad = await client.put(url, json={"code": "AB-12"}, headers=headers)
    assert bad.status_code == 400
    unknown = await client.put(url, json={"bookmaker": "autre", "code": "AB12"}, headers=headers)
    assert unknown.status_code == 400

    public = (await client.get("/api/v1/smart-coupons/day", params={"day": str(DAY)})).json()
    coupon = next(c for c in public["coupons"] if c["profile"] == "equilibre")
    assert coupon["booking_codes"] == [{"bookmaker": "1xbet", "label": "1xBet", "code": "7HQ2K"}]

    await client.put(url, json={"code": ""}, headers=headers)
    listed = (
        await client.get("/api/v1/admin/smart-coupons", params={"day": str(DAY)}, headers=headers)
    ).json()
    coupon = next(c for c in listed["coupons"] if c["profile"] == "equilibre")
    assert coupon["booking_codes"] == []


async def test_daily_coupons_notification_once_all_codes_are_in(
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
    db_factory: Factory,
) -> None:
    """« Coupons du jour disponibles » : rien tant qu'un code manque, puis une seule fois ;
    jamais pour un compte qui l'a désactivée."""
    from sqlalchemy import select

    from footprono.notifications.models import Notification

    m1, m2 = world["m1"], world["m2"]
    await _predict(db_factory, [m1, m2])
    await _evening(db_factory, [m1, m2])
    async with db_factory() as session:
        await smart_coupon.create_daily(session, MORNING)
        day = await smart_coupon.day_coupons(session, DAY, MORNING)
        ids = [c["id"] for c in day["coupons"]]
        assert len(ids) == 2  # « sûr » : aucune sélection ce jour-là
        await smart_coupon.set_booking_code(session, ids[0], "1xbet", "AAAA1")
        assert await smart_coupon.notify_ready(session, MORNING) == 0  # un code manque
        await smart_coupon.set_booking_code(session, ids[1], "1xbet", "BBBB2")
        assert await smart_coupon.notify_ready(session, MORNING) == 1
        assert await smart_coupon.notify_ready(session, MORNING) == 0  # une seule fois
        note = await session.scalar(
            select(Notification).where(Notification.kind == "daily_coupons")
        )
    assert note is not None
    assert note.title == "Coupons du jour disponibles"
    assert note.body.startswith("Équilibré ")
    assert note.data == {"screen": "daily_coupons", "day": str(DAY)}

    headers = await _login(client)
    assert (await client.get("/api/v1/me", headers=headers)).json()["daily_coupons_notifications"]
    off = await client.put(
        "/api/v1/me/preferences", json={"daily_coupons_notifications": False}, headers=headers
    )
    assert off.status_code == 204
    me = (await client.get("/api/v1/me", headers=headers)).json()
    assert me["daily_coupons_notifications"] is False
    async with db_factory() as session:
        await session.execute(
            update(smart_coupon.SmartCoupon).values(notified_at=None)
        )  # nouveau jour simulé
        await session.commit()
        assert await smart_coupon.notify_ready(session, MORNING) == 0  # désactivée
