"""Tables de la montante (suite de paris enchaînés, argent fictif).

Chaque palier est un pari ordinaire (``bets.montante_step_id``) : mise débitée
du solde, gain crédité au solde. La montante fixe la mise de chaque palier (le
gain précédent, moins la part sécurisée) et contrôle la plage de cotes.
Encaisser = arrêter : les gains sont déjà sur le solde.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from footprono.db.base import Base


class Montante(Base):
    __tablename__ = "montantes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    currency: Mapped[str] = mapped_column(String(3))
    start_stake: Mapped[int] = mapped_column(BigInteger)
    # Part de chaque gain mise de côté (reste sur le solde, n'est pas rejouée).
    secure_pct: Mapped[int] = mapped_column(Integer, default=0)
    # active, completed (tous les paliers gagnés), lost, cashed_out
    status: Mapped[str] = mapped_column(String(12), default="active")
    current_step: Mapped[int] = mapped_column(Integer, default=1)
    # Mise du palier en cours (départ, puis gain précédent moins la part sécurisée).
    next_stake: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MontanteStep(Base):
    __tablename__ = "montante_steps"

    id: Mapped[int] = mapped_column(primary_key=True)
    montante_id: Mapped[int] = mapped_column(
        ForeignKey("montantes.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[int] = mapped_column(Integer)
    odds_min: Mapped[Decimal] = mapped_column(Numeric(8, 3))
    odds_max: Mapped[Decimal] = mapped_column(Numeric(8, 3))
    # Pari joué pour ce palier (le dernier, si un remboursement a fait rejouer le palier).
    bet_id: Mapped[int | None] = mapped_column(ForeignKey("bets.id"))
    # Cote totale hors plage acceptée par l'utilisateur après avertissement.
    out_of_range: Mapped[bool] = mapped_column(Boolean, default=False)
    # pending, won, partial, push, lost
    result: Mapped[str] = mapped_column(String(8), default="pending")
