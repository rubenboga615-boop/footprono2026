"""Coupon en direct (maquettes D8 à D15 validées le 13/11/2026).

Pendant trois fenêtres de chaque match suivi : de la pause à la 50e minute, de la 60e à la
63e, de la 75e à la 78e (étude du 13/11/2026 sur 13 347 matchs : chances des coupons
justes à ces trois moments, combinés de plusieurs matchs compris,
docs/ETUDE_COUPONS_DIRECT_2026-11-13.md), le moteur propose pour chaque profil (Sûr,
Équilibré, Audacieux) une sélection par match, choisie comme le Coupon intelligent, et des
combinés de plusieurs matchs (une sélection par match : un bookmaker n'accepte en général
pas deux sélections du même match dans un combiné).

- Chances : celles du direct (``predictions.live_chances.current``), marchés retirés par
  la vérification exclus ; en plus, « plus ou moins de buts » n'est pas proposé en
  Audacieux à la 60e ni en Équilibré à la 75e (à revoir dans l'étude).
- Cotes : relevées par le suivi du direct (``/odds/live``, une requête par passage, et
  seulement quand un match est dans une fenêtre), gardées 3 minutes dans Redis ; une
  sélection sans cote récente n'est pas proposée.
- Publication : rien n'est montré tant que la console ne l'a pas publié ; la console dit
  aussi si les cotes sont celles de 1xBet ou « indicatives » (comparaison des cotes avec
  l'application 1xBet, à la même minute).
- Sûr gratuit (marchés gratuits), Équilibré et Audacieux Premium. Jamais de notification.
"""

import json
import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from footprono.accounts.plans import FREE_MARKETS
from footprono.bookmaker.odds_math import combined_odds
from footprono.console.models import AppSetting
from footprono.engine.live_study import HALF_TIME_PROFILES, family_of_key
from footprono.football.models import Match, MatchStatus, Team

PUBLISHED_KEY = "publication.live_coupons"
ODDS_SOURCE_KEY = "live_coupons.odds_source"  # « 1xbet » ou « indicative »
ODDS_KEY = "live:odds:{}"
ODDS_TTL = 180
ODDS_MAX_AGE = timedelta(seconds=150)
SOURCE = "direct"  # bookmaker inscrit sur une sélection placée en direct

# Fenêtres : (moment de l'étude, ouverture, fermeture) en minutes de jeu.
WINDOWS = (("mi-temps", 45, 50), ("60'", 60, 63), ("75'", 75, 78))
# « Plus ou moins de buts » à revoir dans l'étude du 13/11/2026 pour ce profil et ce moment.
EXCLUDED = {("Audacieux", "60'"), ("Équilibré", "75'")}
GOALS_FAMILY = "Buts du match (plus/moins)"
# Taille des combinés du moteur (au plus ; moins s'il y a moins de matchs ouverts).
COMBO_SIZE = {"Sûr": 2, "Équilibré": 3, "Audacieux": 3}
PREMIUM_PROFILES = ("Équilibré", "Audacieux")


# ---------------------------------------------------------------------- fenêtres


def window(api_status: str | None, minute: int | None) -> tuple[str, int] | None:
    """(moment, minute de fermeture) si le match est dans une fenêtre, sinon None."""
    if api_status == "HT":
        return "mi-temps", 50
    if api_status != "2H" or minute is None:
        return None
    for moment, start, end in WINDOWS:
        if start <= minute <= end and (moment != "mi-temps" or minute >= 46):
            return moment, end
    return None


def odds_wanted(api_status: str | None, minute: int | None) -> bool:
    """Cotes en direct à relever : match dans une fenêtre, ou à une minute de l'ouvrir."""
    if window(api_status, minute) is not None:
        return True
    return api_status == "2H" and minute is not None and minute in (59, 74)


# ------------------------------------------------------------ cotes en direct


def parse_live_odds(entry: dict[str, Any]) -> dict[str, str]:
    """Cotes d'une réponse ``/odds/live`` (un match) dans nos clés « marché|ligne|sélection ».
    Résultat, double chance, buts du match (lignes en ,5), les deux marquent ; cotes
    suspendues écartées."""
    out: dict[str, str] = {}
    sides = {"Home": "home", "Draw": "draw", "Away": "away"}
    double = {"Home or Draw": "1X", "Away or Draw": "X2", "Home or Away": "12"}
    for bet in entry.get("odds") or []:
        name = bet.get("name")
        for v in bet.get("values") or []:
            if v.get("suspended"):
                continue
            value, odd = str(v.get("value")), str(v.get("odd"))
            try:
                if Decimal(odd) <= 1:
                    continue
            except InvalidOperation:
                continue
            if name == "Fulltime Result" and value in sides:
                out[f"1X2||{sides[value]}"] = odd
            elif name == "Double Chance" and value in double:
                out[f"DC||{double[value]}"] = odd
            elif name == "Match Goals" and value in ("Over", "Under"):
                line = str(v.get("handicap") or "")
                if line.endswith(".5"):
                    out[f"OU|{line}|{value.lower()}"] = odd
            elif name == "Both Teams to Score" and value in ("Yes", "No"):
                out[f"BTTS||{value.lower()}"] = odd
    return out


async def store_odds(redis: Redis, by_match: dict[int, dict[str, Any]]) -> None:
    for match_id, data in by_match.items():
        await redis.set(ODDS_KEY.format(match_id), json.dumps(data), ex=ODDS_TTL)


async def load_odds(redis: Redis, match_ids: list[int], now: datetime) -> dict[int, dict[str, Any]]:
    """Cotes en direct récentes (moins de 2 min 30) de chaque match."""
    out = {}
    for mid in match_ids:
        text = await redis.get(ODDS_KEY.format(mid))
        if not text:
            continue
        data = json.loads(text)
        at = datetime.fromisoformat(data["at"])
        if now - at <= ODDS_MAX_AGE:
            out[mid] = data
    return out


# ------------------------------------------------------------- publication


async def settings_of(session: AsyncSession) -> tuple[bool, str]:
    """(publié, source des cotes « 1xbet » ou « indicative ») ; rien publié d'office."""
    published = await session.get(AppSetting, PUBLISHED_KEY)
    source = await session.get(AppSetting, ODDS_SOURCE_KEY)
    return (
        published is not None and published.value == "true",
        source.value if source is not None else "indicative",
    )


async def set_settings(session: AsyncSession, published: bool, source: str) -> None:
    for key, value in (
        (PUBLISHED_KEY, "true" if published else "false"),
        (ODDS_SOURCE_KEY, source),
    ):
        row = await session.get(AppSetting, key)
        if row is None:
            session.add(AppSetting(key=key, value=value))
        else:
            row.value = value
    await session.commit()


# --------------------------------------------------------------- propositions


def pick(
    markets: dict[str, float],
    odds: dict[str, str],
    profile: str,
    moment: str,
    premium: bool,
) -> tuple[str, float, Decimal] | None:
    """Sélection d'un profil pour un match, choisie comme dans l'étude (``coupon_angles``) :
    dans la tranche du profil, la plus probable (la plus proche de la cible pour Sûr) ;
    avec une cote en direct ; marchés gratuits seulement sans Premium."""
    low, high, target = HALF_TIME_PROFILES[profile]
    inside = []
    for key, p in markets.items():
        market = key.split("|", 1)[0]
        family = family_of_key(key)
        if family is None or family.startswith(("Buts de la 1re", "Mi-temps")):
            continue
        if family == GOALS_FAMILY and (profile, moment) in EXCLUDED:
            continue
        if not premium and market not in FREE_MARKETS:
            continue
        if key not in odds or not low <= p < high:
            continue
        inside.append((key, p, Decimal(odds[key])))
    if not inside:
        return None
    if target is None:
        return max(inside, key=lambda c: c[1])
    return min(inside, key=lambda c: (abs(c[1] - target), -c[1]))


def _selection(key: str, p: float, odd: Decimal, match_id: int) -> dict[str, Any]:
    market, line, selection = key.split("|")
    return {
        "match_id": match_id, "market": market, "line": line, "selection": selection,
        "probability": round(p, 4), "odds": str(odd),
    }  # fmt: skip


async def proposals(
    session: AsyncSession, redis: Redis, *, premium: bool, now: datetime | None = None
) -> dict[str, Any]:
    """Matchs ouverts (dans une fenêtre) et combinés du moteur par profil."""
    from footprono.predictions import live_chances

    now = now or datetime.now(UTC)
    published, source = await settings_of(session)
    out: dict[str, Any] = {"published": published, "odds_source": source, "matches": [],
                           "combos": {}}  # fmt: skip
    if not published:
        return out
    home, away = aliased(Team), aliased(Team)
    rows = (
        (
            await session.execute(
                select(Match, home.name, away.name)
                .join(home, home.id == Match.home_team_id)
                .join(away, away.id == Match.away_team_id)
                .where(Match.status == MatchStatus.SCHEDULED, Match.api_status.in_(("HT", "2H")))
            )
        )
        .tuples()
        .all()
    )
    open_: dict[int, tuple[Match, str, str, str, int]] = {}
    for match, h, a in rows:
        w = window(match.api_status, match.live_minute)
        if w is not None:
            open_[match.id] = (match, h, a, *w)
    if not open_:
        return out
    chances = await live_chances.current(session, list(open_))
    odds = await load_odds(redis, list(open_), now)
    picks: dict[str, list[tuple[float, dict[str, Any]]]] = {p: [] for p in HALF_TIME_PROFILES}
    for mid, (match, h, a, moment, closes) in open_.items():
        markets = (chances.get(mid) or {}).get("markets") or {}
        quotes = (odds.get(mid) or {}).get("odds") or {}
        item: dict[str, Any] = {
            "match_id": mid, "home": h, "away": a, "status": match.api_status,
            "minute": match.live_minute, "score": [match.live_home_goals, match.live_away_goals],
            "moment": moment, "closes_at": closes, "picks": {},
        }  # fmt: skip
        for profile in HALF_TIME_PROFILES:
            # Sans Premium : marchés gratuits seulement (Sûr jouable par tous).
            found = pick(markets, quotes, profile, moment, premium)
            if found is None:
                continue
            sel = _selection(*found, mid)
            picks[profile].append((found[1], sel))
            locked = profile in PREMIUM_PROFILES and not premium
            item["picks"][profile] = {"locked": True} if locked else sel
        if item["picks"]:
            out["matches"].append(item)
    out["matches"].sort(key=lambda m: m["closes_at"] - (m["minute"] or 45))
    for profile, options in picks.items():
        if not options:
            continue
        options.sort(key=lambda f: -f[0])
        chosen = [s for _, s in options[: COMBO_SIZE[profile]]]
        chance = math.prod(s["probability"] for s in chosen)
        total = combined_odds(Decimal(s["odds"]) for s in chosen)
        locked = profile in PREMIUM_PROFILES and not premium
        out["combos"][profile] = {
            "size": len(chosen),
            "probability": round(chance, 4),
            "odds": str(total),
            "locked": locked,
            "selections": [] if locked else chosen,
        }
    return out


async def live_offer(
    session: AsyncSession, redis: Redis, match_id: int, key: str, now: datetime
) -> tuple[Decimal, float | None] | None:
    """Cote en direct et chance du moteur d'une sélection pour placer un pari pendant une
    fenêtre ; None si le match n'est pas dans une fenêtre, si le coupon en direct n'est
    pas publié ou si la cote n'est plus proposée."""
    from footprono.predictions import live_chances

    published, _ = await settings_of(session)
    match = await session.get(Match, match_id)
    if not published or match is None or match.status is not MatchStatus.SCHEDULED:
        return None
    if window(match.api_status, match.live_minute) is None:
        return None
    quotes = (await load_odds(redis, [match_id], now)).get(match_id, {}).get("odds") or {}
    if key not in quotes:
        return None
    chance = (
        ((await live_chances.current(session, [match_id])).get(match_id) or {})
        .get("markets", {})
        .get(key)
    )
    if chance is None:
        return None  # marché retiré du direct, ou plus de chance calculée (carton rouge)
    return Decimal(quotes[key]), float(chance)
