"""Montante : plan, pari de chaque palier, avancement au règlement, encaissement.

Règles (validées le 30/09/2026, docs/DESIGN.md) :
- mise de départ libre (5 000 F CFA par défaut), 4 à 8 paliers ;
- une plage de cotes par palier ; hors plage, le pari n'est accepté qu'après
  avertissement explicite de l'utilisateur ;
- les gains se calculent avec la cote réellement jouée, au franc inférieur ;
- option « sécuriser X % de chaque gain » : cette part reste sur le solde et
  n'est pas rejouée ;
- un palier remboursé est rejoué avec la même mise ; un palier perdu arrête
  la montante ; « encaisser » est possible entre deux paliers.
"""

import math
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.accounts.models import User
from footprono.bookmaker import service
from footprono.bookmaker.models import Bet, BetSelection
from footprono.bookmaker.montante_models import Montante, MontanteStep
from footprono.core.errors import AppError, NotFoundError
from footprono.notifications import service as notifications

MIN_STEPS, MAX_STEPS = 4, 8
DEFAULT_START_STAKE = 5_000


def rolled_stake(payout: int, secure_pct: int) -> int:
    """Mise du palier suivant : gain du palier, moins la part sécurisée (au franc inférieur)."""
    return math.floor(payout * (100 - secure_pct) / 100)


async def create(
    session: AsyncSession,
    user: User,
    ranges: list[tuple[Decimal, Decimal]],
    start_stake: int = DEFAULT_START_STAKE,
    secure_pct: int = 0,
) -> Montante:
    if not MIN_STEPS <= len(ranges) <= MAX_STEPS:
        raise AppError(f"une montante compte de {MIN_STEPS} à {MAX_STEPS} paliers")
    if start_stake < service.MIN_STAKE:
        raise AppError(f"mise de départ minimale : {service.MIN_STAKE} {user.currency}")
    if not 0 <= secure_pct <= 90:
        raise AppError("part sécurisée entre 0 et 90 %")
    for low, high in ranges:
        if not Decimal("1.01") <= low <= high:
            raise AppError(f"plage de cotes invalide : {low} à {high}")
    montante = Montante(
        user_id=user.id,
        currency=user.currency,
        start_stake=start_stake,
        secure_pct=secure_pct,
        status="active",
        current_step=1,
        next_stake=start_stake,
    )
    session.add(montante)
    await session.flush()
    for number, (low, high) in enumerate(ranges, start=1):
        session.add(
            MontanteStep(
                montante_id=montante.id, number=number, odds_min=low, odds_max=high,
                out_of_range=False, result="pending",
            )
        )  # fmt: skip
    await session.flush()
    return montante


async def _load(session: AsyncSession, user: User, montante_id: int) -> Montante:
    montante = await session.get(Montante, montante_id)
    if montante is None or montante.user_id != user.id:
        raise NotFoundError(f"montante {montante_id} introuvable")
    return montante


async def _steps(session: AsyncSession, montante_id: int) -> list[MontanteStep]:
    rows = await session.scalars(
        select(MontanteStep)
        .where(MontanteStep.montante_id == montante_id)
        .order_by(MontanteStep.number)
    )
    return list(rows.all())


async def _open_bet(session: AsyncSession, step: MontanteStep) -> Bet | None:
    if step.bet_id is None:
        return None
    bet = await session.get(Bet, step.bet_id)
    return bet if bet is not None and bet.status == "open" else None


async def place_step_bet(
    session: AsyncSession,
    user: User,
    montante_id: int,
    selections: list[service.SelectionIn],
    *,
    accept_out_of_range: bool = False,
) -> Bet:
    """Pari du palier en cours (1 à 3 sélections), à la mise fixée par la montante."""
    montante = await _load(session, user, montante_id)
    if montante.status != "active":
        raise AppError("montante terminée")
    if not 1 <= len(selections) <= 3:
        raise AppError("un palier de montante compte de 1 à 3 sélections")
    step = next(s for s in await _steps(session, montante.id) if s.number == montante.current_step)
    if await _open_bet(session, step) is not None:
        raise AppError(f"le palier {step.number} a déjà un pari en cours")
    bet = await service.place_bet(
        session, user, selections, montante.next_stake, montante_step_id=step.id
    )
    in_range = step.odds_min <= bet.total_odds <= step.odds_max
    if not in_range and not accept_out_of_range:
        # Rien n'est enregistré : la transaction est annulée par l'appelant.
        raise AppError(
            f"cote totale {bet.total_odds} hors de la plage du palier "
            f"({step.odds_min} à {step.odds_max}) : confirmer pour jouer quand même",
            details={"code": "out_of_range", "total_odds": str(bet.total_odds)},
        )
    step.bet_id = bet.id
    step.out_of_range = not in_range
    return bet


async def on_bet_settled(session: AsyncSession, bet: Bet) -> None:
    """Fait avancer (ou arrête) la montante quand le pari d'un palier est réglé."""
    if bet.montante_step_id is None:
        return
    step = await session.get(MontanteStep, bet.montante_step_id)
    assert step is not None
    montante = await session.get(Montante, step.montante_id)
    assert montante is not None
    if montante.status != "active" or step.bet_id != bet.id:
        return
    now = datetime.now(UTC)
    outcome, payout = bet.outcome, bet.payout or 0
    data = {"montante_id": montante.id, "step": step.number, "bet_id": bet.id}

    def tell(kind: str, title: str, body: str) -> None:
        notifications.add(session, montante.user_id, kind, title, body, data)

    if outcome == "lost":
        step.result = "lost"
        montante.status, montante.closed_at = "lost", now
        tell("montante_lost", "Montante perdue", f"Palier {step.number} perdu : montante arrêtée.")
        return
    if outcome == "push":
        # Remboursé : le palier est rejoué avec la même mise.
        step.bet_id, step.result = None, "pending"
        montante.next_stake = payout
        tell(
            "montante_step", f"Palier {step.number} remboursé",
            f"Le palier {step.number} est à rejouer avec la même mise.",
        )  # fmt: skip
        return
    step.result = "won" if outcome == "won" else "partial"
    steps = await _steps(session, montante.id)
    if step.number == len(steps):
        montante.status, montante.closed_at = "completed", now
        montante.next_stake = payout
        tell(
            "montante_completed", "Montante réussie !",
            f"Dernier palier gagné : {notifications.money(payout, montante.currency)}.",
        )  # fmt: skip
        return
    montante.current_step = step.number + 1
    montante.next_stake = rolled_stake(payout, montante.secure_pct)
    tell(
        "montante_step", f"Palier {step.number} validé",
        f"Mise du palier {montante.current_step} : "
        f"{notifications.money(montante.next_stake, montante.currency)}.",
    )  # fmt: skip


async def cash_out(session: AsyncSession, user: User, montante_id: int) -> Montante:
    montante = await _load(session, user, montante_id)
    if montante.status != "active":
        raise AppError("montante déjà terminée")
    step = next(s for s in await _steps(session, montante.id) if s.number == montante.current_step)
    if await _open_bet(session, step) is not None:
        raise AppError("un pari du palier est en cours : encaisser après son règlement")
    montante.status, montante.closed_at = "cashed_out", datetime.now(UTC)
    return montante


async def plan(session: AsyncSession, montante: Montante) -> dict[str, Any]:
    """Tableau de la montante : mises et gains (réels, puis en fourchette), chances.

    - Paliers joués : mise, cote et gain réels.
    - Palier en cours : mise exacte ; paliers suivants : fourchette minimum à
      maximum selon la plage de cotes (gains calculés au franc inférieur).
    - Chance d'aller au bout **selon les cotes** : produit des 1/cote (milieu de
      plage pour les paliers à venir), marge du bookmaker comprise ; **selon le
      moteur** : connue seulement pour les paris déjà choisis.
    - Somme encaissable : ce que la montante a rendu au solde et qui n'est pas
      en jeu (mise du palier suivant comprise tant qu'elle n'est pas jouée).
    """
    steps = await _steps(session, montante.id)
    rows: list[dict[str, Any]] = []
    low = high = montante.next_stake
    secured = 0
    chance_odds = 1.0
    chance_model: float | None = 1.0
    at_risk = False
    for step in steps:
        bet = await session.get(Bet, step.bet_id) if step.bet_id else None
        row: dict[str, Any] = {
            "number": step.number,
            "odds_min": step.odds_min,
            "odds_max": step.odds_max,
            "result": step.result,
            "bet_id": step.bet_id,
            "out_of_range": step.out_of_range,
        }
        if step.number < montante.current_step or (bet is not None and bet.status == "settled"):
            assert bet is not None
            row.update(stake=bet.stake, odds=bet.total_odds, payout=bet.payout)
            if step.number < montante.current_step:
                # Palier gagné et dépassé : seule une partie du gain a été rejouée.
                payout = bet.payout or 0
                secured += payout - rolled_stake(payout, montante.secure_pct)
        elif step.number == montante.current_step and montante.status == "active":
            row["stake"] = montante.next_stake
            if bet is not None:  # pari en cours
                at_risk = True
                row.update(odds=bet.total_odds, potential_payout=bet.potential_payout)
                chance_odds *= float(1 / bet.total_odds)
                probs = await _selection_probs(session, bet.id)
                chance_model = _product(probs) if chance_model is not None else None
                low = high = bet.potential_payout
            else:
                low = math.floor(montante.next_stake * step.odds_min)
                high = math.floor(montante.next_stake * step.odds_max)
                chance_odds *= float(2 / (step.odds_min + step.odds_max))
                chance_model = None
            row["payout_range"] = [low, high]
        elif montante.status == "active":
            stake_low = rolled_stake(low, montante.secure_pct)
            stake_high = rolled_stake(high, montante.secure_pct)
            low = math.floor(stake_low * step.odds_min)
            high = math.floor(stake_high * step.odds_max)
            row.update(stake_range=[stake_low, stake_high], payout_range=[low, high])
            chance_odds *= float(2 / (step.odds_min + step.odds_max))
            chance_model = None
        rows.append(row)
    active = montante.status == "active"
    cashable = secured + (0 if at_risk or not active else montante.next_stake)
    if montante.status == "completed":
        cashable = secured + montante.next_stake
    return {
        "id": montante.id,
        "status": montante.status,
        "currency": montante.currency,
        "start_stake": montante.start_stake,
        "secure_pct": montante.secure_pct,
        "current_step": montante.current_step,
        "steps": rows,
        "final_payout_range": [low, high] if active else None,
        "chance_by_odds": round(chance_odds, 4) if active else None,
        "chance_by_model": round(chance_model, 4) if active and chance_model is not None else None,
        "cashable": cashable,
        "net_result": cashable - montante.start_stake if not at_risk else None,
    }


def _product(values: list[float | None]) -> float | None:
    out = 1.0
    for v in values:
        if v is None:
            return None
        out *= v
    return out


async def _selection_probs(session: AsyncSession, bet_id: int) -> list[float | None]:
    rows = await session.scalars(select(BetSelection).where(BetSelection.bet_id == bet_id))
    return [s.model_probability for s in rows]
