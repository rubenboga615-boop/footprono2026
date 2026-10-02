from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from footprono.db.base import Base


class Payment(Base):
    """Paiement de Premium. Statut décidé par la vérification auprès du
    prestataire (jamais par la seule notification reçue)."""

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Compte supprimé : le paiement reste (comptabilité), détaché de la personne.
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    provider: Mapped[str] = mapped_column(String(16))
    transaction_id: Mapped[str] = mapped_column(String(64), unique=True)
    amount: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    days: Mapped[int] = mapped_column(Integer)
    # pending, accepted, refused, error, cancelled (compte supprimé avant la fin)
    status: Mapped[str] = mapped_column(String(12), default="pending", index=True)
    payment_url: Mapped[str | None] = mapped_column(String(512))
    provider_status: Mapped[str | None] = mapped_column(String(40))
    method: Mapped[str | None] = mapped_column(String(40))
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
