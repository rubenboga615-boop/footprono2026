from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
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
    # Notification « coupons du jour disponibles » envoyée (une fois, quand tous les
    # coupons du jour ont leur code).
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LiveCouponPick(Base):
    """Sélection proposée par le coupon en direct (maquette D15) : une par match, profil et
    moment, enregistrée la première fois qu'elle est proposée, puis réglée après le match.
    Sert à la Fiabilité des coupons en direct (annoncé contre gagné) ; rien n'est effacé."""

    __tablename__ = "live_coupon_picks"
    __table_args__ = (UniqueConstraint("match_id", "profile", "moment"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), index=True)
    profile: Mapped[str] = mapped_column(String(16))
    moment: Mapped[str] = mapped_column(String(16))  # mi-temps, 60', 75'
    minute: Mapped[int | None] = mapped_column(SmallInteger)
    market: Mapped[str] = mapped_column(String(32))
    line: Mapped[str] = mapped_column(String(16))
    selection: Mapped[str] = mapped_column(String(32))
    probability: Mapped[float] = mapped_column(Float)
    odds: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    proposed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # win, half_win, push, half_loss, loss ; null tant que le match n'est pas réglé.
    result: Mapped[str | None] = mapped_column(String(10), index=True)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LiveWindowOdds(Base):
    """Cotes du direct d'un match à l'ouverture d'une fenêtre du coupon en direct (pause,
    60e, 75e), avec le score et les cartons rouges du relevé : pour l'étude « chances du
    direct avec ou sans les statistiques du match » demandée le 13/11/2026."""

    __tablename__ = "live_window_odds"
    __table_args__ = (UniqueConstraint("match_id", "moment"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), index=True)
    moment: Mapped[str] = mapped_column(String(16))
    taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    state: Mapped[list[int] | None] = mapped_column(JSONB)
    odds: Mapped[dict[str, str]] = mapped_column(JSONB)
