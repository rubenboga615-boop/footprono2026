"""Types et conversions communs aux sources."""

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from footprono.football.models import OddsTiming


@dataclass(frozen=True)
class OddsQuote:
    bookmaker: str
    market: str
    line: Decimal
    timing: OddsTiming
    selection: str
    price: Decimal


@dataclass
class ParseIssues:
    """Anomalies rencontrées pendant l'analyse d'un fichier (jamais ignorées en silence)."""

    items: list[str] = field(default_factory=list)

    def add(self, message: str) -> None:
        self.items.append(message)


def to_int(value: str | None) -> int | None:
    if value is None or value.strip() == "":
        return None
    return int(float(value))


def to_decimal(value: str | float | None) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip()
    if text == "" or text.lower() in {"nan", "none", "null"}:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None
