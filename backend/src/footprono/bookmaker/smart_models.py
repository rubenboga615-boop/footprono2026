from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from footprono.db.base import Base


class SmartCoupon(Base):
    """Coupon du jour généré automatiquement (un par profil), réglé après les matchs.

    Sert d'historique public : chaque coupon est enregistré **avant** les matchs,
    gagné ou perdu, rien n'est effacé.
    """

    __tablename__ = "smart_coupons"
    __table_args__ = (UniqueConstraint("day", "profile"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    profile: Mapped[str] = mapped_column(String(16))
    size: Mapped[int] = mapped_column(SmallInteger)
    # [{match_id, home, away, competition, kickoff_at, market, line, selection,
    #   odds, model_probability, result}]
    selections: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    total_odds: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    probability: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(
        String(8), default="pending"
    )  # pending, won, lost, partial, void
    # Codes de réservation saisis par l'administrateur après avoir recréé le coupon chez
    # le bookmaker : {"1xbet": "7HQ2K"}. Le joueur copie le code et le colle chez lui.
    booking_codes: Mapped[dict[str, str]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
