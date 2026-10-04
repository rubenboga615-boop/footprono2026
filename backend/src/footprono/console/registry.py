"""Catalogue des actions de la console.

Chaque action est déclarée une fois, dans le code du serveur (``actions.py``) :
titre, famille, explication, risque, réglages. La console affiche le catalogue
tel que le serveur le décrit : une action ajoutée par une mise à jour du serveur
apparaît d'elle-même, sans nouvelle version de l'interface.
"""

import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from footprono.core.errors import AppError, NotFoundError

if TYPE_CHECKING:
    from footprono.console.jobs import JobContext

FAMILIES = ("Données", "Moteur", "Application", "Comptes", "Diagnostic")
Family = Literal["Données", "Moteur", "Application", "Comptes", "Diagnostic"]
# lecture : ne change rien ; modifie : écrit en base (rejouable) ;
# irreversible : effet visible des utilisateurs, confirmation demandée.
Risk = Literal["lecture", "modifie", "irreversible"]
ParamKind = Literal["choice", "choices", "int", "bool", "text"]
Options = Sequence[tuple[str, str]] | Callable[[], Sequence[tuple[str, str]]]


@dataclass(frozen=True)
class Param:
    """Réglage d'une action : liste, choix multiple, nombre, oui/non ou texte court."""

    name: str
    label: str
    kind: ParamKind
    default: Any = None
    # (valeur, libellé) ; une fonction pour une liste qui suit le référentiel.
    options: Options = ()
    minimum: int | None = None
    maximum: int | None = None
    help: str | None = None
    pattern: str | None = None

    def choices(self) -> list[tuple[str, str]]:
        return list(self.options() if callable(self.options) else self.options)

    def describe(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "name": self.name,
            "label": self.label,
            "kind": self.kind,
            "default": self.default,
        }
        if self.kind in ("choice", "choices"):
            out["options"] = [{"value": v, "label": lbl} for v, lbl in self.choices()]
        if self.minimum is not None:
            out["min"] = self.minimum
        if self.maximum is not None:
            out["max"] = self.maximum
        if self.help:
            out["help"] = self.help
        return out

    def clean(self, value: Any) -> Any:
        """Valeur reçue de la console, vérifiée ; la valeur par défaut si absente."""
        if value is None:
            value = self.default
        if value is None:
            raise _invalid(f"« {self.label} » est obligatoire")
        if self.kind == "bool":
            if not isinstance(value, bool):
                raise _invalid(f"« {self.label} » : oui ou non attendu")
            return value
        if self.kind == "int":
            if isinstance(value, bool) or not isinstance(value, int):
                raise _invalid(f"« {self.label} » : nombre entier attendu")
            if self.minimum is not None and value < self.minimum:
                raise _invalid(f"« {self.label} » : au moins {self.minimum}")
            if self.maximum is not None and value > self.maximum:
                raise _invalid(f"« {self.label} » : au plus {self.maximum}")
            return value
        if self.kind == "text":
            if not isinstance(value, str) or len(value) > 200:
                raise _invalid(f"« {self.label} » : texte de 200 caractères au plus")
            value = value.strip()
            if self.pattern and not re.fullmatch(self.pattern, value):
                raise _invalid(f"« {self.label} » : valeur non valide")
            return value
        allowed = {v for v, _ in self.choices()}
        if self.kind == "choice":
            if value not in allowed:
                raise _invalid(f"« {self.label} » : valeur inconnue {value!r}")
            return value
        if not isinstance(value, list) or not value:
            raise _invalid(f"« {self.label} » : choisir au moins une valeur")
        unknown = [v for v in value if v not in allowed]
        if unknown:
            raise _invalid(f"« {self.label} » : valeurs inconnues {unknown}")
        # Ordre du catalogue, sans doublon.
        return [v for v, _ in self.choices() if v in value]


Runner = Callable[["JobContext", dict[str, Any]], Awaitable[str]]


@dataclass(frozen=True)
class Action:
    """Une action de la console ; ``run`` renvoie le résumé affiché à la fin."""

    id: str
    title: str
    family: Family
    description: str
    risk: Risk
    run: Runner
    params: tuple[Param, ...] = ()
    # Une seule tâche exclusive à la fois (collecte, import, pronostics : mêmes tables,
    # même quota API-Football, même téléphone).
    exclusive: bool = False
    # Coût et durée annoncés avant le lancement (texte libre, ex. « ≈ 40 requêtes »).
    cost: str | None = None
    duration: str | None = None
    # Peut être arrêtée proprement en cours de route.
    stoppable: bool = False
    tags: tuple[str, ...] = field(default_factory=tuple)

    def describe(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "family": self.family,
            "description": self.description,
            "risk": self.risk,
            "exclusive": self.exclusive,
            "cost": self.cost,
            "duration": self.duration,
            "stoppable": self.stoppable,
            "confirm": self.risk == "irreversible",
            "params": [p.describe() for p in self.params],
        }

    def validate(self, values: dict[str, Any]) -> dict[str, Any]:
        unknown = set(values) - {p.name for p in self.params}
        if unknown:
            raise _invalid(f"réglages inconnus : {', '.join(sorted(unknown))}")
        return {p.name: p.clean(values.get(p.name)) for p in self.params}


_REGISTRY: dict[str, Action] = {}


def register(action: Action) -> Action:
    if action.id in _REGISTRY:
        raise RuntimeError(f"action déclarée deux fois : {action.id}")
    if action.family not in FAMILIES:
        raise RuntimeError(f"famille inconnue pour {action.id} : {action.family}")
    _REGISTRY[action.id] = action
    return action


def _load() -> None:
    # Les actions s'enregistrent à l'import de leur module.
    from footprono.console import actions  # noqa: F401


def get_action(action_id: str) -> Action:
    _load()
    try:
        return _REGISTRY[action_id]
    except KeyError:
        raise NotFoundError(f"action inconnue : {action_id}") from None


def all_actions() -> list[Action]:
    _load()
    order = {f: i for i, f in enumerate(FAMILIES)}
    return sorted(_REGISTRY.values(), key=lambda a: (order[a.family], a.title))


def catalog() -> list[dict[str, Any]]:
    return [a.describe() for a in all_actions()]


class InvalidParamsError(AppError):
    status_code = 422
    code = "invalid_params"


def _invalid(message: str) -> AppError:
    return InvalidParamsError(message)
