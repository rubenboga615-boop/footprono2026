"""Tables du plan de jeu et des alertes de cote (maquettes 29 et 30 du nouveau visage).

- ``play_plans`` : budget de la semaine, limite de perte, mise maximale, rappel d'une heure,
  pause. Une limite plus stricte s'applique tout de suite ; une limite relevée ou retirée
  attend 24 heures (``pending`` et ``pending_at``), pour éviter les décisions sous le coup
  d'une perte.
- ``odds_alerts`` : « préviens-moi quand la cote de cette sélection atteint X » (``kind`` =
  ``selection``) ou « dès qu'un pari dépasse la cote de N points » (``kind`` = ``gap``).
- ``odds_alert_hits`` : une alerte au plus par match et par alerte.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from footprono.db.base import Base


class PlayPlan(Base):
    __tablename__ = "play_plans"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    weekly_budget: Mapped[int | None] = mapped_column(Integer)
    loss_limit: Mapped[int | None] = mapped_column(Integer)
    max_stake: Mapped[int | None] = mapped_column(Integer)
    reminder: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    pause_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Limites relevées ou retirées, appliquées 24 h après ``pending_at`` :
    # {"weekly_budget": 8000 | null, ...}
    pending: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    pending_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OddsAlert(Base):
    __tablename__ = "odds_alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10))  # selection, gap
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    # Alerte sur une sélection : match, marché, cote visée, et la cote au moment de la création.
    match_id: Mapped[int | None] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE"), index=True
    )
    market: Mapped[str | None] = mapped_column(String(40))
    line: Mapped[str | None] = mapped_column(String(10))
    selection: Mapped[str | None] = mapped_column(String(40))
    target_odds: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    start_odds: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    # Alerte d'écart : moteur au-dessus de la cote d'au moins ``min_gap`` (0,08 = 8 points).
    min_gap: Mapped[float | None] = mapped_column(Float)
    # Dernier déclenchement (alerte sur une sélection : une seule fois, puis éteinte).
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OddsAlertHit(Base):
    """Déclenchement d'une alerte : un par match et par alerte, avec ce qui a été vu."""

    __tablename__ = "odds_alert_hits"
    __table_args__ = (UniqueConstraint("alert_id", "match_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    alert_id: Mapped[int] = mapped_column(
        ForeignKey("odds_alerts.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"))
    market: Mapped[str] = mapped_column(String(40))
    line: Mapped[str] = mapped_column(String(10), default="", server_default="")
    selection: Mapped[str] = mapped_column(String(40))
    from_odds: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    odds: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    bookmaker: Mapped[str] = mapped_column(String(40))
    engine: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FollowedTeam(Base):
    """Équipe suivie par un joueur (maquette 26 « Suivie », filtre « Suivis » de la maquette 6)."""

    __tablename__ = "followed_teams"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    team_id: Mapped[int] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
