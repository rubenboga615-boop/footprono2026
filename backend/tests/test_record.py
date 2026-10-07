"""Mon bilan : paris réglés du joueur seulement, réussite, annoncé contre réalisé."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from footprono.accounts import service as accounts
from footprono.bookmaker.models import Bet, BetSelection
from footprono.bookmaker.record import MIN_BAND

from .conftest import make_settings
from .test_bets import _login, world  # noqa: F401 (fixture)


def _bet(user_id: int, stake: int, odds: str, status: str, outcome: str | None, payout: int | None,
         placed: datetime, sels: list[tuple[int, str, str, float | None]]) -> Bet:  # fmt: skip
    bet = Bet(
        user_id=user_id, kind="single" if len(sels) == 1 else "combo", stake=stake,
        currency="XOF", total_odds=Decimal(odds), potential_payout=int(stake * float(odds)),
        status=status, outcome=outcome, payout=payout, placed_at=placed,
    )  # fmt: skip
    bet.selections = [  # type: ignore[attr-defined]
        BetSelection(match_id=m, market=market, line="", selection="home", odds=Decimal(odds),
                     bookmaker="1xBet", model_probability=p, result=result)
        for m, market, result, p in sels
    ]  # fmt: skip
    return bet


async def test_record_counts_only_my_settled_bets(
    db_factory: async_sessionmaker[AsyncSession],
    world: dict[str, Any],  # noqa: F811
    client: AsyncClient,
) -> None:
    now = datetime.now(UTC)
    me, m1, m2 = world["user_id"], world["m1"], world["m2"]
    async with db_factory() as session:
        other = await accounts.register(
            session, make_settings(), phone="+22997222222", password="12345678",
            display_name="Ama", country="TG", adult=True,
        )  # fmt: skip
        rows: list[tuple[Bet, list[BetSelection]]] = []

        def add(bet: Bet) -> None:
            sels = bet.selections  # type: ignore[attr-defined]
            rows.append((bet, sels))

        # 25 simples annoncés à 65 % (cote 1,60) : 15 gagnés, 10 perdus, il y a 10 jours.
        old = now - timedelta(days=10)
        for i in range(25):
            won = i < 15
            add(_bet(me, 1000, "1.60", "settled", "won" if won else "lost", 1600 if won else 0,
                     old, [(m1, "1X2", "win" if won else "loss", 0.65)]))  # fmt: skip
        # Combiné récent : une sélection gagnée, une remboursée.
        add(_bet(me, 5000, "2.00", "settled", "won", 9000, now - timedelta(days=1),
                 [(m1, "OU", "win", 0.55), (m2, "BTTS", "push", 0.5)]))  # fmt: skip
        add(_bet(me, 3000, "1.90", "void", None, 3000, now, [(m2, "1X2", "pending", 0.5)]))
        add(_bet(me, 30000, "1.90", "open", None, None, now, [(m2, "1X2", "pending", 0.5)]))
        add(_bet(other.id, 1000, "1.60", "settled", "lost", 0, now, [(m1, "1X2", "loss", 0.9)]))
        for bet, sels in rows:
            session.add(bet)
            await session.flush()
            for s in sels:
                s.bet_id = bet.id
                session.add(s)
        await session.commit()

    assert (await client.get("/api/v1/me/record")).status_code == 401
    r = await client.get("/api/v1/me/record", headers=await _login(client))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["bets"] == {
        "settled": 26,
        "open": 1,
        "won": 16,
        "lost": 10,
        "push": 0,
        "partial": 0,
    }
    assert body["staked"] == 25 * 1000 + 5000
    assert body["returned"] == 15 * 1600 + 9000
    assert body["profit"] == body["returned"] - body["staked"]
    assert body["yield"] == round(body["profit"] / body["staked"], 4)

    markets = {m["key"]: m for m in body["by_market"]}
    assert markets["1X2"] == {"key": "1X2", "won": 15, "lost": 10, "push": 0, "rate": 0.6}
    assert markets["BTTS"]["push"] == 1
    assert markets["BTTS"]["rate"] is None
    assert body["by_competition"][0]["key"] == "EPL"

    bands = {(b["low"], b["high"]): b for b in body["calibration"]}
    band = bands[(0.6, 0.7)]
    assert band["selections"] == 25
    assert band["announced"] == 0.65
    assert band["observed"] == 0.6
    assert band["implied"] == 0.625  # 1 / 1,60
    assert MIN_BAND <= 25
    assert band["enough"] is True
    assert bands[(0.5, 0.6)]["enough"] is False  # une seule sélection : peu de paris
    assert 0.9 not in [b["announced"] for b in body["calibration"]]  # pari de l'autre joueur

    # En-tête du bookmaker : tous les paris (pas seulement les 100 chargés), mêmes totaux.
    summary = (await client.get("/api/v1/me/bets-summary", headers=await _login(client))).json()
    assert summary == {
        "bets": 28,
        "settled": 26,
        "staked": body["staked"],
        "returned": body["returned"],
        "yield": body["yield"],
        "at_stake": 30000,
        "last_30_days": 9000 - 5000 + 15 * 600 - 10 * 1000,
    }

    # Cette semaine : 38 000 (combiné, annulé, en cours) ; la précédente : 25 000.
    assert body["stakes_7d"] == 38000
    assert body["stakes_prev_7d"] == 25000
    assert body["rising"] is False  # moins du double

    by_odds = {b["low"]: b for b in body["by_odds"]}
    assert by_odds[1.0]["bets"] == 25  # simples à 1,60
    assert by_odds[1.0]["won"] == 15
    assert by_odds[1.0]["announced"] == 0.65
    assert by_odds[1.0]["profit"] == 15 * 1600 - 25 * 1000
    assert by_odds[2.0]["bets"] == 1  # combiné à 2,00
    assert by_odds[2.0]["announced"] == round(0.55 * 0.5, 4)
    assert by_odds[2.0]["high"] == 5.0
