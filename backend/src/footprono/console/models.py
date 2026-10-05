from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from footprono.db.base import Base


class AdminJob(Base):
    """Une action lancée depuis la console : réglages, état, résultat, auteur."""

    __tablename__ = "admin_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    action: Mapped[str] = mapped_column(String(48), index=True)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    # queued, running, succeeded, failed, cancelled
    status: Mapped[str] = mapped_column(String(12), default="queued", index=True)
    # Grosse tâche (collecte, import, pronostics) : une seule à la fois.
    exclusive: Mapped[bool] = mapped_column(Boolean, default=False)
    progress: Mapped[float | None] = mapped_column(Float)
    # Étape en cours (indice dans les étapes annoncées par l'action).
    step: Mapped[int | None] = mapped_column(Integer)
    summary: Mapped[str | None] = mapped_column(String(400))
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    stop_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Dernier signe de vie (ligne de journal, progression) : une tâche « running » muette
    # depuis longtemps a été interrompue (redémarrage du serveur).
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AdminJobLine(Base):
    """Ligne du journal d'une tâche, lue par la console au fur et à mesure."""

    __tablename__ = "admin_job_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("admin_jobs.id", ondelete="CASCADE"), index=True)
    n: Mapped[int] = mapped_column(Integer)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    text: Mapped[str] = mapped_column(Text)


class AppSetting(Base):
    """Réglage du serveur modifiable depuis la console (canal des alertes…)."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
