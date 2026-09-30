"""Tables des prédictions.

Chaque exécution du moteur (``prediction_runs``) est conservée avec sa version
et ses réglages ; chaque prédiction (``match_predictions``) est rattachée à une
exécution et n'est jamais modifiée. On garde ainsi l'historique de ce qui a
été annoncé avant chaque match, ce qui permettra de publier une fiabilité
mesurée sur des prédictions réellement faites à l'avance (et pas recalculées
après coup).
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, Float, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from footprono.db.base import Base


class PredictionRun(Base):
    __tablename__ = "prediction_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    engine_version: Mapped[str] = mapped_column(String(32))
    as_of: Mapped[date] = mapped_column(Date)  # seuls les matchs joués avant cette date comptent
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16))
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    report: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class MatchPrediction(Base):
    __tablename__ = "match_predictions"
    __table_args__ = (UniqueConstraint("run_id", "match_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("prediction_runs.id", ondelete="CASCADE"))
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Buts attendus (après correction) et paramètres de la loi des scores.
    lambda_home: Mapped[float] = mapped_column(Float)
    lambda_away: Mapped[float] = mapped_column(Float)
    rho: Mapped[float] = mapped_column(Float)
    share_home: Mapped[float] = mapped_column(Float)
    share_away: Mapped[float] = mapped_column(Float)
    # « marché|ligne|sélection » -> [gagné, demi-gagné, remboursé, demi-perdu].
    markets: Mapped[dict[str, list[float]]] = mapped_column(JSONB)
    # Statistique -> moyennes attendues (domicile, extérieur), dispersion, arbitre.
    counts: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    # Contexte connu avant le match (classement, enjeu…), pour l'explication.
    context: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
