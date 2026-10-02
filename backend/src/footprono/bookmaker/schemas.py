from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class OfferOut(BaseModel):
    """Une sélection jouable : cote réelle du bookmaker et probabilité du moteur."""

    market: str
    line: str | None
    selection: str
    odds: Decimal
    bookmaker: str
    label: str
    fetched_at: datetime
    model_probability: float | None
    model_fair_odds: float | None
    # Première cote relevée pour cette sélection chez ce bookmaker (mouvement des cotes).
    opening_odds: Decimal | None = None
    opened_at: datetime | None = None
    # Dernière mise à jour de la cote chez la source, et dernier relevé de FootProno.
    source_updated_at: datetime | None = None
    checked_at: datetime | None = None


class OddsPointOut(BaseModel):
    """Une cote relevée : enregistrée à ``at`` (seulement quand elle a changé)."""

    at: datetime
    odds: Decimal


class OddsHistoryOut(BaseModel):
    market: str
    line: str | None
    selection: str
    bookmaker: str
    label: str
    points: list[OddsPointOut]
    # Dernier relevé où la cote actuelle était encore proposée, inchangée.
    last_seen_at: datetime


class SelectionIn(BaseModel):
    match_id: int
    market: str
    line: str = ""
    selection: str
    odds: Decimal | None = Field(
        default=None, description="cote affichée ; refus si la cote actuelle est plus basse"
    )


class BetIn(BaseModel):
    stake: int = Field(gt=0)
    selections: list[SelectionIn] = Field(min_length=1)


class BetSelectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    match_id: int
    market: str
    line: str
    selection: str
    odds: Decimal
    bookmaker: str
    model_probability: float | None
    result: str
    # Pour l'affichage (renseignés par l'API) : équipes et coup d'envoi du match.
    home_team: str | None = None
    away_team: str | None = None
    kickoff_at: datetime | None = None


class BetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    stake: int
    currency: str
    total_odds: Decimal
    potential_payout: int
    status: str
    outcome: str | None
    payout: int | None
    placed_at: datetime
    settled_at: datetime | None
    montante_step_id: int | None
    selections: list[BetSelectionOut]
