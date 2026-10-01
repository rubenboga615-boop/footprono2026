"""Tables des comptes et du portefeuille.

Le solde est de l'argent **fictif**. Chaque mouvement est une ligne du
journal (``wallet_entries``) avec le solde après opération : le solde se
reconstruit toujours à partir du journal, jamais modifié sans trace.
Montants en entiers dans l'unité de la devise (franc CFA : pas de centimes).
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from footprono.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Numéro au format international E.164 (« +22997000000 »), identifiant de connexion.
    phone: Mapped[str] = mapped_column(String(16), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(40))
    country: Mapped[str] = mapped_column(String(2))  # ISO 3166-1 alpha-2
    currency: Mapped[str] = mapped_column(String(3))  # ISO 4217
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # « user » ou « admin » (administration : abonnements, suivi des données).
    role: Mapped[str] = mapped_column(String(8), default="user")
    # Premium actif jusqu'à cette date (essai de 7 jours à l'inscription, puis
    # activation par l'administrateur en attendant le paiement Mobile Money).
    premium_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def is_premium(self, now: datetime) -> bool:
        return self.premium_until is not None and self.premium_until > now


class Wallet(Base):
    __tablename__ = "wallets"
    __table_args__ = (CheckConstraint("balance >= 0", name="balance_not_negative"),)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    currency: Mapped[str] = mapped_column(String(3))
    balance: Mapped[int] = mapped_column(BigInteger)
    last_refill_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SubscriptionEvent(Base):
    """Historique des périodes Premium : essai, activation par l'administrateur, paiement."""

    __tablename__ = "subscription_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # trial, admin_grant, admin_revoke, payment
    days: Mapped[int] = mapped_column(Integer)
    premium_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    admin_id: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WalletEntry(Base):
    """Un mouvement du portefeuille : crédit (> 0) ou débit (< 0)."""

    __tablename__ = "wallet_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    amount: Mapped[int] = mapped_column(BigInteger)
    balance_after: Mapped[int] = mapped_column(BigInteger)
    # opening, refill, stake, payout, void, correction
    kind: Mapped[str] = mapped_column(String(16))
    bet_id: Mapped[int | None] = mapped_column(Integer, index=True)
    note: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
