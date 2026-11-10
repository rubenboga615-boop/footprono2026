"""Coupon intelligent : génération, coupons du jour, règlement, historique, marchés retirés."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono.accounts import service as accounts
from footprono.bookmaker import smart_coupon
from footprono.bookmaker.smart_models import SmartCoupon
from footprono.engine.markets import offered
from footprono.football.models import Match, MatchStatus

from .conftest import make_premium, make_settings
from .test_bets import NOW, _login, quote, world  # noqa: F401 (fixture partagée)
from .test_montante import _predict

Factory = async_sessionmaker[AsyncSession]
DAY = (NOW + timedelta(days=1)).date()
KICKOFF = datetime(DAY.year, DAY.month, DAY.day, 20, tzinfo=UTC)
MORNING = datetime(DAY.year, DAY.month, DAY.day, 8, 5, tzinfo=UTC)


class _FrozenClock(datetime):
    """Horloge du coupon arrêtée à NOW (celle des matchs de test) : sans elle, une suite
    lancée avant minuit et finie après voit « demain » changer de jour en cours de route."""

    @classmethod
    def now(cls, tz: Any = None) -> "_FrozenClock":
        moment = NOW if tz is None else NOW.astimezone(tz)
        return cls.fromtimestamp(moment.timestamp(), moment.tzinfo)


@pytest.fixture(autouse=True)
def _frozen_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(smart_coupon, "datetime", _FrozenClock)


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
    assert not offered("SOT_1X2||home")  # tirs cadrés « le plus de » : retiré le 06/11/2026
    assert offered("SOT_OU|4.5|over")
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
    headers = await _login(client)
    await make_premium(db_factory, "+22997111111")

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
        # Un match ne sert qu'à un seul profil par jour : Équilibré a pris m1 et m2.
        assert created["audacieux"] == "aucune sélection"
        again = await smart_coupon.create_daily(session, MORNING)
        assert again["equilibre"] == "déjà créé"
        # Équilibré et Audacieux : cote totale d'au moins 2,00 (Sûr : pas de minimum).
        for c in (await session.scalars(select(SmartCoupon))).all():
            if c.profile != "sur":
                assert c.total_odds >= Decimal("2.00")
        # Coupon d'un autre jour, sur les mêmes matchs (+2,5 buts), pour le règlement.
        balanced = (await session.scalars(select(SmartCoupon))).one()
        session.add(
            SmartCoupon(
                day=DAY - timedelta(days=1), profile="audacieux", size=2,
                selections=[
                    {**sel, "market": "OU", "line": "2.5", "selection": "over", "odds": "1.90"}
                    for sel in balanced.selections
                ],
                total_odds=Decimal("3.61"), probability=0.25, status="pending",
            )
        )  # fmt: skip
        await session.commit()

    # m1 1-0 : +2,5 buts perdu, coupon perdu sans attendre m2 ; « équilibré » en cours.
    assert await _result(db_factory, m1, 1, 0) == {"won": 0, "lost": 1, "partial": 0, "void": 0}
    # m2 2-1 : « équilibré » gagné.
    assert await _result(db_factory, m2, 2, 1) == {"won": 1, "lost": 0, "partial": 0, "void": 0}

    public = (await client.get("/api/v1/smart-coupons/history")).json()
    status = {c["profile"]: c["status"] for c in public["coupons"]}
    assert status == {"equilibre": "won", "audacieux": "lost"}
    lost = next(c for c in public["coupons"] if c["profile"] == "audacieux")
    # La sélection de m2 est notée après coup (avant : « en attente » pour toujours).
    assert {s["match_id"]: s["result"] for s in lost["selections"]} == {m1: "loss", m2: "win"}
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
    # Dernière sélection : la plus petite cote qui suffit parmi les suivantes les plus
    # probables (essai réel du 07/11/2026 : 25 visé, 37,31 obtenu).
    near = [_fake(1, "2.00", 0.80), _fake(2, "2.00", 0.79), _fake(3, "2.50", 0.70),
            _fake(4, "1.60", 0.68), _fake(5, "1.30", 0.66)]  # fmt: skip
    closer = smart_coupon.target_coupon(near, Decimal("5"), max_size=12)
    assert [pk.match.id for pk in closer] == [1, 2, 5]  # 2 x 2 x 1,30 = 5,2 (et non 10)
    # Hors de la fenêtre (6e suivante et au-delà) : jamais prise.
    far = [
        _fake(1, "2.00", 0.8),
        *[_fake(i, "3.00", 0.7) for i in range(2, 7)],
        _fake(7, "1.05", 0.6),
    ]
    assert [pk.match.id for pk in smart_coupon.target_coupon(far, Decimal("5"), max_size=12)] == [
        1,
        2,
    ]
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
    await make_premium(db_factory, "+22997111111")

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

    impossible = await gen(profile="grosse", period="tomorrow", target_odds="10", size=1)
    assert impossible["coupon"] is None
    assert "Impossible d'atteindre une cote de 10" in impossible["message"]
    # Cote visée de 2 à 10 (plan du 10/11/2026, étape 4).
    too_big = await client.get(
        "/api/v1/smart-coupon",
        params={"profile": "grosse", "period": "tomorrow", "target_odds": "500"},
        headers=headers,
    )
    assert too_big.status_code == 400
    assert "de 2 à 10" in too_big.text
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
    comp = without_m1["coupon"]["selections"][0]["competition"]
    no_comp = await gen(profile="equilibre", period="tomorrow", size=2, exclude_competitions=[comp])
    assert no_comp["coupon"] is None  # tous les matchs du jour sont dans ce championnat
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
    await make_premium(db_factory, "+22997111111")
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

    # Sans compte ni Premium : profil, cote, chance et avancement, mais ni sélections ni code.
    anonymous = (await client.get("/api/v1/smart-coupons/day", params={"day": str(DAY)})).json()
    hidden = next(c for c in anonymous["coupons"] if c["profile"] == "equilibre")
    assert (hidden["locked"], hidden["selections"], hidden["booking_codes"]) == (True, [], [])
    assert hidden["selection_count"] == 2
    assert hidden["total_odds"]
    assert hidden["probability"]

    player = await _login(client)
    await make_premium(db_factory, "+22997111111")
    day = (
        await client.get("/api/v1/smart-coupons/day", params={"day": str(DAY)}, headers=player)
    ).json()
    coupon = next(c for c in day["coupons"] if c["profile"] == "equilibre")
    assert coupon["locked"] is False
    assert coupon["display_status"] == "live"
    assert coupon["validated"] == 0
    assert coupon["booking_codes"] == []
    states = {s["match_id"]: s for s in coupon["selections"]}
    assert (states[m1]["state"], states[m1]["minute"], states[m1]["score"]) == ("live", 58, [1, 0])
    assert states[m2]["state"] == "upcoming"
    assert set(day["summary"]) == {"yesterday", "last_30_days", "last_30_days_by_profile"}

    url = f"/api/v1/admin/smart-coupons/{coupon['id']}/booking-code"
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

    shown = (
        await client.get("/api/v1/smart-coupons/day", params={"day": str(DAY)}, headers=player)
    ).json()
    coupon = next(c for c in shown["coupons"] if c["profile"] == "equilibre")
    assert coupon["booking_codes"] == [{"bookmaker": "1xbet", "label": "1xBet", "code": "7HQ2K"}]
    public = (await client.get("/api/v1/smart-coupons/day", params={"day": str(DAY)})).json()
    assert next(c for c in public["coupons"] if c["profile"] == "equilibre")["booking_codes"] == []
    # Historique : le coupon pas encore réglé reste masqué sans Premium.
    history = (await client.get("/api/v1/smart-coupons/history")).json()
    pending = [c for c in history["coupons"] if c["status"] == "pending"]
    assert pending
    assert all(c["locked"] and c["selections"] == [] for c in pending)

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
    await make_premium(db_factory, "+22997111111")
    async with db_factory() as session:
        await smart_coupon.create_daily(session, MORNING)
        # Deux matchs seulement : Équilibré les prend, Audacieux est ajouté à la main.
        balanced = (await session.scalars(select(SmartCoupon))).one()
        session.add(
            SmartCoupon(
                day=DAY, profile="audacieux", size=2, selections=balanced.selections,
                total_odds=Decimal("3.42"), probability=0.36, status="pending",
            )
        )  # fmt: skip
        await session.commit()
        day = await smart_coupon.day_coupons(session, DAY, MORNING)
        ids = [c["id"] for c in day["coupons"]]
        assert len(ids) == 2  # « sûr » : aucune sélection ce jour-là
        await smart_coupon.set_booking_code(session, ids[0], "1xbet", "AAAA1")
        assert await smart_coupon.notify_ready(session, MORNING) == 0  # un code manque
        await smart_coupon.set_booking_code(session, ids[1], "1xbet", "BBBB2")
        # Un compte gratuit n'est pas prévenu : il ne peut pas les ouvrir.
        await accounts.register(
            session, make_settings(), phone="+22997222222", password="12345678",
            display_name="Gratuit", country="TG", adult=True,
        )  # fmt: skip
        await session.commit()
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


async def test_history_pages_and_30_days_split_by_profile(
    client: AsyncClient, db_factory: Factory
) -> None:
    today = NOW.date()
    async with db_factory() as session:
        for d in range(1, 31):  # 30 jours, 3 coupons par jour : 90 coupons réglés
            for profile, p, won in (("sur", 0.6, d % 2 == 0), ("equilibre", 0.45, d % 3 == 0),
                                    ("audacieux", 0.25, d % 5 == 0)):  # fmt: skip
                session.add(
                    SmartCoupon(
                        day=today - timedelta(days=d), profile=profile, size=0, selections=[],
                        total_odds=Decimal("2.00"), probability=p,
                        status="won" if won else "lost",
                    )
                )  # fmt: skip
        await session.commit()

    first = (await client.get("/api/v1/smart-coupons/history")).json()
    assert len(first["coupons"]) == smart_coupon.HISTORY_LIMIT
    assert first["has_more"] is True
    second = (await client.get("/api/v1/smart-coupons/history", params={"offset": 60})).json()
    assert len(second["coupons"]) == 30
    assert second["has_more"] is False
    ids = [c["id"] for c in first["coupons"] + second["coupons"]]
    assert len(set(ids)) == 90  # rien de perdu ni de répété entre les pages
    assert first["stats"]["sur"] == {
        "label": "Sûr", "settled": 30, "won": 15, "announced": 0.6, "observed": 0.5,
    }  # fmt: skip

    day = (await client.get("/api/v1/smart-coupons/day")).json()
    month = day["summary"]["last_30_days_by_profile"]
    assert (month["sur"]["won"], month["sur"]["settled"]) == (15, 30)
    assert (month["equilibre"]["won"], month["audacieux"]["won"]) == (10, 6)
    assert month["audacieux"]["announced"] == 0.25
    assert day["summary"]["last_30_days"] == {"settled": 90, "won": 31}


def test_reasons_always_about_what_the_bet_counts() -> None:
    """Raisons du coupon : des corners pour un pari sur les corners (jamais des buts), et pour
    un pari sur les buts, les buts attendus par le moteur (essai réel du 06/11/2026)."""
    from types import SimpleNamespace

    season = {
        "goals_for": 1.4, "goals_against": 1.1, "corners": 5.2, "corners_against": 4.6,
        "cards": 2.1, "shots": 12.0, "shots_on_target": 4.3,
    }  # fmt: skip
    analysis: dict[str, Any] = {
        "season": {"home": season, "away": season},
        "form": {"home": [{"result": "W"}, {"result": "L"}], "away": []},
        "head_to_head": [{"score": "2-1"}],
        "expected_goals": (1.3, 0.9),
    }

    def pick(market: str) -> Any:
        return SimpleNamespace(
            offer=SimpleNamespace(market=market), home="Everton", away="Coventry"
        )

    corners = smart_coupon.reasons(analysis, pick("CORNERS_OU"))
    assert corners[0].startswith("Corners par match (obtenus + concédés)")
    assert not any("buts" in r for r in corners)
    assert smart_coupon.reasons(analysis, pick("CARDS_OU"))[0].startswith("Cartons reçus")
    goals = smart_coupon.reasons(analysis, pick("OU"))
    assert goals[0] == "Buts attendus par le moteur : Everton 1,3, Coventry 0,9 (2,2 au total)"
    result = smart_coupon.reasons(analysis, pick("1X2"))
    assert result[1].endswith("Everton DV, Coventry —")  # le plus récent à droite


def test_count_bet_shows_its_corners_not_the_score() -> None:
    """Pari « plus de 7,5 corners » réglé : ses corners (« 11 corners (6-5) »), pas le score."""
    from footprono.football.models import Match, MatchStatus

    match = Match(id=7, status=MatchStatus.FINISHED, home_goals=0, away_goals=0)
    state = smart_coupon.live_state(
        {"result": "win", "market": "CORNERS_OU"}, match, {(7, "corners"): (6, 5)}
    )
    assert state["count"] == [6, 5]
    assert state["count_label"] == "corners"
    goals = smart_coupon.live_state({"result": "win", "market": "OU"}, match, {})
    assert goals["score"] == [0, 0]
    assert "count" not in goals


def test_daily_coupons_hold_at_most_one_goal_bet() -> None:
    """Décision du 07/11/2026 : au plus un pari de buts par coupon du jour (ils en
    remplissaient 14 sur 21 alors qu'en réel ils font à peine mieux qu'une prévision
    naïve) ; au-delà, le match garde son meilleur angle hors buts."""
    from types import SimpleNamespace

    def pk(mid: int, market: str, p: float) -> smart_coupon.Pick:
        offer = SimpleNamespace(odds=Decimal("1.30"), quote_id=mid, market=market)
        match = SimpleNamespace(id=mid, kickoff_at=None)
        return smart_coupon.Pick(match, "A", "B", "EPL", offer, p)  # type: ignore[arg-type]

    sur = smart_coupon.PROFILES["sur"]
    per_match = [
        [pk(1, "OU", 0.86), pk(1, "1X2", 0.80)],
        [pk(2, "BTTS", 0.84), pk(2, "DC", 0.78)],
        [pk(3, "TEAM_OU_HOME", 0.83)],  # pas d'autre angle : laissé de côté
        [pk(4, "DC", 0.81)],
    ]
    out = smart_coupon.balanced_angles(sur, per_match, quota=1)
    assert [(p.match.id, p.offer.market) for p in out] == [(1, "OU"), (2, "DC"), (4, "DC")]
    assert sum(smart_coupon.is_goal_market(p.offer.market) for p in out) == 1


def test_each_player_gets_a_near_best_coupon_and_not_all_the_same() -> None:
    """Proposition du 07/11/2026 : 1 000 joueurs, plus le même coupon pour tous ; chacun à
    97 % au moins de la chance du meilleur ; même coupon toute la journée pour un joueur ;
    la chance moyenne reste celle du meilleur coupon (à un point près)."""
    from collections import Counter
    from datetime import date
    from types import SimpleNamespace

    def pick(mid: int, p: float) -> smart_coupon.Pick:
        offer = SimpleNamespace(odds=Decimal("1.33"), quote_id=mid, market="DC")
        return smart_coupon.Pick(SimpleNamespace(id=mid), "A", "B", "EPL", offer, p)  # type: ignore[arg-type]

    # Équilibré un samedi : beaucoup de sélections juste sous 75 %, puis d'autres plus bas.
    ranked = [pick(i, 0.749 - 0.0008 * i) for i in range(12)] + [
        pick(100 + i, 0.70 - 0.01 * i) for i in range(10)
    ]
    best = ranked[:3]
    day = date(2026, 11, 7)
    coupons = []
    for player in range(1, 1001):
        chosen, spare = smart_coupon.vary(
            ranked, 3, smart_coupon.player_rng(player, day, "equilibre", 0)
        )
        assert (len(chosen), len(spare)) == (3, smart_coupon.ALTERNATIVES)
        assert smart_coupon.chance(chosen) >= 0.97 * smart_coupon.chance(best)
        assert all(pk not in spare for pk in chosen)
        coupons.append(tuple(pk.match.id for pk in chosen))
    shared = Counter(coupons).most_common(1)[0][1]
    assert len(set(coupons)) > 50
    assert shared < 100  # le coupon le plus donné : moins d'un joueur sur dix
    mean = (
        sum(
            smart_coupon.chance([ranked[[pk.match.id for pk in ranked].index(i)] for i in c])
            for c in coupons
        )
        / 1000
    )
    assert mean >= smart_coupon.chance(best) - 0.01
    # Le même joueur, le même jour : le même coupon ; « Un autre coupon » : le tirage suivant.
    again, _ = smart_coupon.vary(ranked, 3, smart_coupon.player_rng(7, day, "equilibre", 0))
    other, _ = smart_coupon.vary(ranked, 3, smart_coupon.player_rng(7, day, "equilibre", 1))
    assert tuple(pk.match.id for pk in again) == coupons[6]
    assert tuple(pk.match.id for pk in other) != coupons[6]
    # Sans joueur (coupons du jour, publiés pour tous) : toujours le meilleur.
    assert smart_coupon.vary(ranked, 3, None)[0] == best
    # Peu de sélections à égalité : le meilleur coupon, sans tirage.
    lonely = [pick(1, 0.749), pick(2, 0.70), pick(3, 0.66), pick(4, 0.62)]
    assert (
        smart_coupon.vary(lonely, 3, smart_coupon.player_rng(1, day, "equilibre", 0))[0]
        == lonely[:3]
    )


async def test_history_says_which_days_had_no_coupon(
    client: AsyncClient, db_factory: Factory
) -> None:
    """Rapport du 09/11/2026 : un jour sans coupon passait pour un oubli ; et le premier
    jour de l'historique n'était pas indiqué."""
    today = NOW.date()
    async with db_factory() as session:
        for back, profiles in ((1, ("sur",)), (3, ("sur", "equilibre", "audacieux"))):
            for profile in profiles:
                session.add(
                    SmartCoupon(
                        day=today - timedelta(days=back), profile=profile, size=0,
                        selections=[], total_odds=Decimal("1.50"), probability=0.6,
                        status="lost",
                    )
                )  # fmt: skip
        await session.commit()
    history = (await client.get("/api/v1/smart-coupons/history")).json()
    assert history["first_day"] == str(today - timedelta(days=3))
    assert history["days"] == [
        {"day": str(today - timedelta(days=1)), "missing": ["Équilibré", "Audacieux"],
         "none": False},
        {"day": str(today - timedelta(days=2)), "missing": ["Sûr", "Équilibré", "Audacieux"],
         "none": True},
    ]  # fmt: skip


def test_automatic_picks_skip_stale_and_tiny_odds() -> None:
    """Rapport du 10/11/2026 : cotes de la CAN que la source n'avait pas mises à jour depuis
    un mois, et une cote de 1,02, dans les coupons proposés."""
    from footprono.bookmaker.service import Offer
    from footprono.football.models import Match

    now = NOW

    def offer(odds: str, updated_days: float | None, selection: str) -> Offer:
        return Offer(
            "1X2", "", selection, Decimal(odds), "1xBet", 1, now, "Match Winner",
            source_updated_at=None if updated_days is None else now - timedelta(days=updated_days),
        )  # fmt: skip

    offers = {
        "1X2||home": offer("1.80", 0.5, "home"),  # récente : gardée
        "1X2||draw": offer("3.40", 31, "draw"),  # un mois sans mise à jour : écartée
        "1X2||away": offer("1.02", None, "away"),  # trop basse : écartée
    }
    probs = {"1X2||home": 0.55, "1X2||draw": 0.25, "1X2||away": 0.2}
    picks = smart_coupon._picks(Match(id=1), "A", "B", "EPL", offers, probs, now)
    assert [p.offer.selection for p in picks] == ["home"]
