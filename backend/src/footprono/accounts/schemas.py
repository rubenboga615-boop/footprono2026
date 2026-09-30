from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RegisterIn(BaseModel):
    phone: str = Field(examples=["+229 97 00 00 00"])
    password: str
    display_name: str = Field(min_length=1, max_length=40)
    country: str = Field(min_length=2, max_length=2, examples=["BJ"])
    adult: bool = Field(description="l'utilisateur déclare avoir 18 ans ou plus")


class LoginIn(BaseModel):
    phone: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 (type de jeton, pas un secret)


class WalletOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    currency: str
    balance: int
    last_refill_at: datetime | None


class PlanOut(BaseModel):
    name: str = Field(description="free ou premium")
    premium_until: datetime | None
    days_left: int
    free_markets: list[str]
    premium_price: int
    premium_currency: str


class MeOut(BaseModel):
    id: int
    phone: str
    display_name: str
    country: str
    currency: str
    created_at: datetime
    role: str
    plan: PlanOut
    wallet: WalletOut
    virtual_money: bool = True  # argent fictif : rappel pour l'application


class WalletEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    amount: int
    balance_after: int
    kind: str
    bet_id: int | None
    note: str | None
    created_at: datetime
