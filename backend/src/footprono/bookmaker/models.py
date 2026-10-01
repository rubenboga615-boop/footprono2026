"""Tables des paris.

Un pari (``bets``) regroupe une ou plusieurs sélections (``bet_selections``) ;
un combiné ne réunit que des matchs différents. Chaque sélection garde la cote
réellement jouée (bookmaker et relevé d'origine) et la probabilité du moteur au
moment du pari. Montants en entiers dans la devise de l'utilisateur.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from footprono.db.base import Base


class Bet(Base):
    __tablename__ = "bets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(8))  # single, combo
    stake: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    total_odds: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    potential_payout: Mapped[int] = mapped_column(BigInteger)
    # open (en cours), settled (réglé), void (annulé et remboursé)
    status: Mapped[str] = mapped_column(String(8), default="open", index=True)
    # Réglé : won, lost, push (remboursé), partial (demi-gain ou demi-perte)
    outcome: Mapped[str | None] = mapped_column(String(8))
    payout: Mapped[int | None] = mapped_column(BigInteger)
    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Nombre de règlements (> 1 : score corrigé après coup, pari réglé à nouveau).
    settlements: Mapped[int] = mapped_column(Integer, default=0)
    # Palier de montante auquel ce pari appartient (phase 4, étape montante).
    montante_step_id: Mapped[int | None] = mapped_column(Integer, index=True)


class BetSelection(Base):
    __tablename__ = "bet_selections"

    id: Mapped[int] = mapped_column(primary_key=True)
    bet_id: Mapped[int] = mapped_column(ForeignKey("bets.id", ondelete="CASCADE"), index=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    # Clé du moteur : marché, ligne (vide si sans objet), sélection.
    market: Mapped[str] = mapped_column(String(24))
    line: Mapped[str] = mapped_column(String(8), default="")
    selection: Mapped[str] = mapped_column(String(24))
    odds: Mapped[Decimal] = mapped_column(Numeric(8, 3))
    bookmaker: Mapped[str] = mapped_column(String(32))
    odds_quote_id: Mapped[int | None] = mapped_column(ForeignKey("bookmaker_odds.id"))
    model_probability: Mapped[float | None] = mapped_column(Float)
    # pending, win, half_win, push, half_loss, loss
    result: Mapped[str] = mapped_column(String(10), default="pending")
