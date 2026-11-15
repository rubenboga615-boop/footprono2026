from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
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
    __table_args__ = (UniqueConstraint("day", "profile", "engine"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    profile: Mapped[str] = mapped_column(String(16))
    # Comparaison des moteurs (K5, 15/11/2026) : 1 = coupons du jour de tous, 2 = moteur 2,
    # montrés seulement en mode comparaison (jamais dans le bilan public du moteur 1).
    engine: Mapped[int] = mapped_column(SmallInteger, default=1, server_default="1")
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


class EngineProposal(Base):
    """Comparaison des moteurs (maquette K6) : un pari proposé par le moteur 1 ou le moteur 2
    en mode comparaison (Coupon intelligent, suggestions de palier), enregistré la première
    fois qu'il est proposé dans la journée, joué ou non, puis réglé (bilan à mise fixe).
    Les coupons du jour sont déjà gardés dans ``smart_coupons`` (colonne ``engine``)."""

    __tablename__ = "engine_proposals"
    __table_args__ = (UniqueConstraint("engine", "source", "key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    engine: Mapped[int] = mapped_column(SmallInteger)  # 1 ou 2
    source: Mapped[str] = mapped_column(String(16))  # coupon, montante
    # Jour et sélections : le même pari reproposé le même jour ne compte qu'une fois.
    key: Mapped[str] = mapped_column(String(400))
    # [{match_id, market, line, selection, odds, model_probability, result}]
    selections: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    total_odds: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    probability: Mapped[float] = mapped_column(Float)
    proposed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # pending, won, lost, partial, void
    status: Mapped[str] = mapped_column(String(8), default="pending", index=True)
    payout: Mapped[int | None] = mapped_column(Integer)  # gain pour la mise fixe (STAKE)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EngineMatchChances(Base):
    """Comparaison des moteurs (K6) : chances 1-N-2 des deux moteurs pour un match, relevées
    avant le coup d'envoi (la dernière avant le match compte), pour la log loss sur les mêmes
    matchs."""

    __tablename__ = "engine_match_chances"

    match_id: Mapped[int] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE"), primary_key=True
    )
    engine1: Mapped[dict[str, float]] = mapped_column(JSONB)  # {home, draw, away}
    engine2: Mapped[dict[str, float]] = mapped_column(JSONB)
    calibrated: Mapped[bool] = mapped_column(Boolean)  # moteur 2 calé sur la référence
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
