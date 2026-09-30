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
