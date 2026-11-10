"""Publication des pronostics des coupes d'Europe et des sélections nationales.

Interrupteurs de la console (Moteur → « Pronostics publiés : coupes et sélections »),
gardés en base (``app_settings``). Tant que la console n'a rien choisi, la valeur de
départ est celle du serveur (``FP_CUPS_PREDICTIONS``, ``FP_NATIONS_PREDICTIONS``).
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from footprono.console.models import AppSetting
from footprono.core.config import Settings

CUPS_KEY = "publication.cups"
NATIONS_KEY = "publication.nations"
# Chances en direct (plan du 10/11/2026, étape 6) : jamais publiées d'office.
LIVE_KEY = "publication.live"


@dataclass(frozen=True)
class Publication:
    cups: bool
    nations: bool


async def _flag(session: AsyncSession, key: str, default: bool) -> bool:
    row = await session.get(AppSetting, key)
    return default if row is None else row.value == "true"


async def publication(session: AsyncSession, settings: Settings) -> Publication:
    return Publication(
        cups=await _flag(session, CUPS_KEY, settings.cups_predictions),
        nations=await _flag(session, NATIONS_KEY, settings.nations_predictions),
    )


async def live_published(session: AsyncSession) -> bool:
    return await _flag(session, LIVE_KEY, False)


async def set_flag(session: AsyncSession, key: str, value: bool) -> None:
    row = await session.get(AppSetting, key)
    text = "true" if value else "false"
    if row is None:
        session.add(AppSetting(key=key, value=text))
    else:
        row.value = text
    await session.commit()
