from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from footprono.football.schemas import MatchOut


class SelectionOut(BaseModel):
    """Une sélection d'un marché, avec ses issues de règlement et sa cote juste."""

    market: str
    line: str | None
    selection: str
    probability: float  # gagné
    half_win: float
    push: float  # remboursé
    half_loss: float
    fair_odds: float | None  # cote d'espérance nulle (None : ne peut pas gagner)


class PredictionRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    engine_version: str
    as_of: date
    started_at: datetime
    finished_at: datetime | None
    status: str
    parameters: dict[str, Any]
    report: dict[str, Any]


class ExpectedGoals(BaseModel):
    home: float
    away: float


class PredictionOut(BaseModel):
    match_id: int
    run_id: int
    engine_version: str
    as_of: date
    created_at: datetime
    expected_goals: ExpectedGoals
    markets: list[SelectionOut]
    # Corners, cartons, tirs et analyse détaillée : Premium (None en version gratuite).
    counts: dict[str, Any] | None
    context: dict[str, Any] | None
    plan: str = Field(description="free ou premium : formule appliquée à cette réponse")
    locked_markets: list[str] = Field(
        default_factory=list, description="marchés disponibles en Premium, non inclus ici"
    )


class PredictionSummary(BaseModel):
    """L'essentiel pour une liste de matchs : 1X2, +2,5 buts, les deux marquent."""

    run_id: int
    engine_version: str
    created_at: datetime
    expected_goals: ExpectedGoals
    home: SelectionOut
    draw: SelectionOut
    away: SelectionOut
    over_2_5: SelectionOut
    both_score: SelectionOut


class UpcomingMatchOut(BaseModel):
    match: MatchOut
    prediction: PredictionSummary | None  # None : pas encore prédit (voir le rapport)
