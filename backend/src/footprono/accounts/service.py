"""Inscription, connexion et mouvements du portefeuille."""

import re
from datetime import UTC, datetime, timedelta

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.accounts.models import User, Wallet, WalletEntry
from footprono.accounts.security import hash_password, verify_password
from footprono.core.config import Settings
from footprono.core.errors import AppError

# Pays du lancement (Afrique de l'Ouest, zone franc CFA UEMOA) → devise.
COUNTRIES: dict[str, tuple[str, str]] = {
    "BJ": ("Bénin", "XOF"),
    "BF": ("Burkina Faso", "XOF"),
    "CI": ("Côte d'Ivoire", "XOF"),
    "GW": ("Guinée-Bissau", "XOF"),
    "ML": ("Mali", "XOF"),
    "NE": ("Niger", "XOF"),
    "SN": ("Sénégal", "XOF"),
    "TG": ("Togo", "XOF"),
}
MIN_PASSWORD = 8
_PHONE = re.compile(r"^\+[1-9]\d{7,14}$")


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


class UnauthorizedError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthorized"


class InsufficientFundsError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "insufficient_funds"


def normalize_phone(raw: str) -> str:
    """« +229 97 00 00 00 » → « +22997000000 » ; format international obligatoire."""
    phone = re.sub(r"[\s.\-()]", "", raw)
    if phone.startswith("00"):
        phone = "+" + phone[2:]
    if not _PHONE.match(phone):
        raise AppError("numéro invalide : format international attendu, par exemple +229 97000000")
    return phone


async def register(
    session: AsyncSession,
    settings: Settings,
    *,
    phone: str,
    password: str,
    display_name: str,
    country: str,
    adult: bool,
) -> User:
    if not adult:
        raise AppError("l'application est réservée aux personnes de 18 ans ou plus")
    country = country.upper()
    if country not in COUNTRIES:
        raise AppError(f"pays non disponible : {country} (disponibles : {', '.join(COUNTRIES)})")
    if len(password) < MIN_PASSWORD:
        raise AppError(f"mot de passe trop court ({MIN_PASSWORD} caractères minimum)")
    phone = normalize_phone(phone)
    if await session.scalar(select(User.id).where(User.phone == phone)) is not None:
        raise ConflictError("un compte existe déjà avec ce numéro")
    currency = COUNTRIES[country][1]
    user = User(
        phone=phone,
        password_hash=hash_password(password),
        display_name=display_name.strip()[:40],
        country=country,
        currency=currency,
    )
    session.add(user)
    await session.flush()
    session.add(Wallet(user_id=user.id, currency=currency, balance=0))
    await session.flush()
    await move(session, user.id, settings.starting_balance, "opening", note="solde de départ")
    return user


async def authenticate(session: AsyncSession, phone: str, password: str) -> User:
    try:
        phone = normalize_phone(phone)
    except AppError:
        raise UnauthorizedError("numéro ou mot de passe incorrect") from None
    user = await session.scalar(select(User).where(User.phone == phone))
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        raise UnauthorizedError("numéro ou mot de passe incorrect")
    return user


async def move(
    session: AsyncSession,
    user_id: int,
    amount: int,
    kind: str,
    *,
    bet_id: int | None = None,
    note: str | None = None,
) -> WalletEntry:
    """Crédite (> 0) ou débite (< 0) le portefeuille et l'inscrit au journal.

    Le portefeuille est verrouillé le temps de la transaction : deux opérations
    simultanées ne peuvent pas dépenser le même solde. Un débit qui rendrait le
    solde négatif est refusé.
    """
    wallet = await session.scalar(select(Wallet).where(Wallet.user_id == user_id).with_for_update())
    if wallet is None:
        raise AppError("portefeuille introuvable")
    if wallet.balance + amount < 0:
        raise InsufficientFundsError(
            f"solde insuffisant : {wallet.balance} {wallet.currency} disponibles"
        )
    wallet.balance += amount
    entry = WalletEntry(
        user_id=user_id,
        amount=amount,
        balance_after=wallet.balance,
        kind=kind,
        bet_id=bet_id,
        note=note,
    )
    session.add(entry)
    await session.flush()
    return entry


async def refill(session: AsyncSession, settings: Settings, user_id: int) -> WalletEntry:
    """Rechargement gratuit jusqu'au solde de départ (argent fictif), sous conditions."""
    wallet = await session.scalar(select(Wallet).where(Wallet.user_id == user_id).with_for_update())
    if wallet is None:
        raise AppError("portefeuille introuvable")
    if wallet.balance >= settings.refill_below:
        raise AppError(
            f"rechargement possible seulement sous {settings.refill_below} {wallet.currency}"
        )
    now = datetime.now(UTC)
    interval = timedelta(days=settings.refill_interval_days)
    if wallet.last_refill_at is not None and now - wallet.last_refill_at < interval:
        next_at = wallet.last_refill_at + interval
        raise AppError(f"prochain rechargement possible le {next_at:%d/%m/%Y à %H:%M} (UTC)")
    wallet.last_refill_at = now
    return await move(
        session, user_id, settings.starting_balance - wallet.balance, "refill", note="rechargement"
    )
