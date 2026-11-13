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
- But ou carton rouge (relecture du 13/11/2026) : chaque relevé de cotes garde le score et
  les cartons rouges du moment ; une cote relevée avant un changement n'est plus proposée
  ni jouable, et rien n'est jouable dans les 2 minutes qui suivent un but (VAR).
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
from footprono.core.errors import AppError
from footprono.engine.live_study import HALF_TIME_PROFILES, family_of_key
from footprono.football.models import LiveSnapshot, Match, MatchEvent, MatchStatus, Team

PUBLISHED_KEY = "publication.live_coupons"
ODDS_SOURCE_KEY = "live_coupons.odds_source"  # « 1xbet » ou « indicative »
ODDS_KEY = "live:odds:{}"
ODDS_TTL = 180
ODDS_MAX_AGE = timedelta(seconds=150)
SOURCE = "direct"  # bookmaker inscrit sur une sélection placée en direct
GOAL_PAUSE = timedelta(minutes=2)  # rien de jouable juste après un but (VAR)
AFTER_GOAL = "la cote a changé après un but ou un carton rouge : attends la prochaine cote"

# Fenêtres : (moment de l'étude, ouverture, fermeture) en minutes de jeu.
WINDOWS = (("mi-temps", 45, 50), ("60'", 60, 63), ("75'", 75, 78))
# « Plus ou moins de buts » à revoir dans l'étude du 13/11/2026 pour ce profil et ce moment.
EXCLUDED = {("Audacieux", "60'"), ("Équilibré", "75'")}
GOALS_FAMILY = "Buts du match (plus/moins)"
# Taille des combinés du moteur (au plus ; moins s'il y a moins de matchs ouverts).
COMBO_SIZE = {"Sûr": 2, "Équilibré": 3, "Audacieux": 3}
PREMIUM_PROFILES = ("Équilibré", "Audacieux")
# Décision du fondateur (13/11/2026, après le premier coupon en production) : proposer
# seulement si la chance du moteur dépasse la chance selon la cote (1/cote) d'au moins
# 3 points, sélection comme combiné ; écart de plus de 20 points écarté (erreur probable
# du moteur, Tunisie - Libye du 13/11). Remplace l'indépendance vis-à-vis des cotes pour le
# seul coupon en direct ; le bilan en argent de la Fiabilité dira si c'est rentable.
EDGE = 0.03
MAX_EDGE = 0.20
# Sélections nationales : moteur peu fiable si une équipe a moins de matchs joués en 2 ans.
MIN_NATION_MATCHES = 8
NATION_DAYS = 730
# « En test » tant qu'il y a moins de propositions réglées, ou si le bilan est négatif.
TRIAL_SETTLED = 200
STAKE = 1000


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


def entry_problem(
    entry: dict[str, Any], score: list[Any] | None, paused: bool = False
) -> str | None:
    """Pourquoi les cotes d'une réponse ``/odds/live`` ne sont pas gardées (None : gardées).
    Écartées si la source les suspend (``blocked``, ``finished`` ; ``stopped`` aussi, sauf
    à la mi-temps où le jeu est arrêté mais aucun but ne peut tomber) ou si elles ont été
    relevées à un autre score que le relevé des matchs (cotes d'avant un but)."""
    status = entry.get("status") or {}
    for key, why in (("blocked", "bloquées"), ("finished", "terminées"), ("stopped", "arrêtées")):
        if status.get(key) and not (key == "stopped" and paused):
            return f"cotes {why} par la source"
    teams = entry.get("teams") or {}
    goals = [(teams.get(s) or {}).get("goals") for s in ("home", "away")]
    if score is None or None in goals or goals != score:
        return f"score des cotes {goals} différent du match {score}"
    if not parse_live_odds(entry):
        return "aucune cote ouverte sur nos marchés"
    return None


def entry_current(entry: dict[str, Any], score: list[Any] | None, paused: bool = False) -> bool:
    return entry_problem(entry, score, paused) is None


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


def _red(detail: str | None) -> bool:
    d = (detail or "").lower()
    return "red" in d or "second yellow" in d


async def match_states(session: AsyncSession, match_ids: list[int]) -> dict[int, list[int]]:
    """État de chaque match : [buts domicile, buts extérieur, cartons rouges]."""
    if not match_ids:
        return {}
    rows = await session.execute(
        select(Match.id, Match.live_home_goals, Match.live_away_goals).where(
            Match.id.in_(match_ids)
        )
    )
    out = {mid: [h or 0, a or 0, 0] for mid, h, a in rows.tuples()}
    cards = await session.execute(
        select(MatchEvent.match_id, MatchEvent.detail).where(
            MatchEvent.match_id.in_(match_ids), MatchEvent.kind == "Card"
        )
    )
    for mid, detail in cards.tuples():
        if _red(detail) and mid in out:
            out[mid][2] += 1
    return out


async def goal_times(session: AsyncSession, match_ids: list[int]) -> dict[int, datetime]:
    """Moment où le score actuel a été vu pour la première fois (après un but, ou un but
    annulé), d'après les relevés du direct ; absent si le score n'a jamais changé."""
    out: dict[int, datetime] = {}
    for mid in match_ids:
        snaps = (
            (
                await session.execute(
                    select(LiveSnapshot.taken_at, LiveSnapshot.home_goals, LiveSnapshot.away_goals)
                    .where(LiveSnapshot.match_id == mid)
                    .order_by(LiveSnapshot.taken_at.desc())
                    .limit(200)
                )
            )
            .tuples()
            .all()
        )
        if not snaps:
            continue
        score = (snaps[0][1], snaps[0][2])
        first = None
        for taken_at, h, a in snaps:
            if (h, a) != score:
                break
            first = taken_at
        else:
            continue  # score inchangé sur tous les relevés gardés
        if first is not None:
            out[mid] = first
    return out


async def usable_odds(
    session: AsyncSession, odds: dict[int, dict[str, Any]], now: datetime
) -> tuple[dict[int, dict[str, Any]], set[int]]:
    """Cotes encore valables : relevées au score et aux cartons rouges actuels, et pas dans
    les 2 minutes après un but. Renvoie aussi les matchs écartés pour cette raison."""
    ids = list(odds)
    states = await match_states(session, ids)
    goals = await goal_times(session, ids)
    kept, after_goal = {}, set()
    for mid, data in odds.items():
        same = data.get("state") is not None and data.get("state") == states.get(mid)
        recent = mid in goals and now - goals[mid] < GOAL_PAUSE
        if same and not recent:
            kept[mid] = data
        else:
            after_goal.add(mid)
    return kept, after_goal


async def thin_nations(session: AsyncSession, match_ids: list[int], now: datetime) -> set[int]:
    """Matchs de sélections nationales (prévision du moteur des sélections) dont une équipe
    a joué moins de ``MIN_NATION_MATCHES`` matchs en 2 ans : écartés du coupon en direct."""
    from sqlalchemy import func, or_

    from footprono.predictions.models import MatchPrediction

    nation_ids = set(
        await session.scalars(
            select(MatchPrediction.match_id).where(
                MatchPrediction.match_id.in_(match_ids), MatchPrediction.context.has_key("nations")
            )
        )
    )
    out: set[int] = set()
    since = (now - timedelta(days=NATION_DAYS)).date()
    for mid in nation_ids:
        match = await session.get(Match, mid)
        if match is None:
            continue
        for team in (match.home_team_id, match.away_team_id):
            played = await session.scalar(
                select(func.count())
                .select_from(Match)
                .where(
                    or_(Match.home_team_id == team, Match.away_team_id == team),
                    Match.status == MatchStatus.FINISHED,
                    Match.match_date >= since,
                )
            )
            if (played or 0) < MIN_NATION_MATCHES:
                out.add(mid)
                break
    return out


def _profit(result: str, odds: Decimal) -> float:
    """Gain net d'une mise de ``STAKE`` sur une sélection réglée."""
    o = float(odds)
    return STAKE * {
        "win": o - 1, "half_win": (o - 1) / 2, "push": 0.0, "half_loss": -0.5, "loss": -1.0,
    }.get(result, 0.0)  # fmt: skip


async def in_trial(session: AsyncSession) -> bool:
    """« En test » : moins de ``TRIAL_SETTLED`` propositions réglées, ou bilan négatif."""
    from footprono.bookmaker.smart_models import LiveCouponPick

    rows = (
        (
            await session.execute(
                select(LiveCouponPick.result, LiveCouponPick.odds).where(
                    LiveCouponPick.result.is_not(None)
                )
            )
        )
        .tuples()
        .all()
    )
    return len(rows) < TRIAL_SETTLED or sum(_profit(r or "", o) for r, o in rows) < 0


async def record_window_odds(
    session: AsyncSession, redis: Redis, now: datetime | None = None
) -> int:
    """Cotes du direct de chaque match dans une fenêtre, gardées une fois par moment, pour
    l'étude « chances du direct avec ou sans les statistiques du match » (les statistiques
    sont déjà gardées à chaque minute dans ``live_snapshots``)."""
    from sqlalchemy.dialects.postgresql import insert

    from footprono.bookmaker.smart_models import LiveWindowOdds

    now = now or datetime.now(UTC)
    rows = []
    matches = await session.scalars(
        select(Match).where(
            Match.status == MatchStatus.SCHEDULED, Match.api_status.in_(("HT", "2H"))
        )
    )
    open_ = {m.id: w for m in matches if (w := window(m.api_status, m.live_minute)) is not None}
    for mid, data in (await load_odds(redis, list(open_), now)).items():
        rows.append({
            "match_id": mid, "moment": open_[mid][0], "taken_at": now,
            "state": data.get("state"), "odds": data.get("odds") or {},
        })  # fmt: skip
    if not rows:
        return 0
    result = await session.execute(
        insert(LiveWindowOdds)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["match_id", "moment"])
        .returning(LiveWindowOdds.id)
    )
    added = len(result.all())
    await session.commit()
    return added


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
    avec une cote en direct, au moins 3 points sous la chance du moteur (au plus 20) ;
    marchés gratuits seulement sans Premium."""
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
        implied = 1 / float(odds[key])
        if p < implied + EDGE or p - implied > MAX_EDGE:
            continue  # cote pas assez généreuse, ou écart trop beau pour être vrai
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
        # Relecture du 13/11 (14 h 07) : le moteur moins confiant que la cote est signalé,
        # jamais écarté (docs/MOTEUR.md : choisir sur un désaccord avec la cote retient
        # surtout les cas où la cote a raison).
        "implied": round(1 / float(odd), 4), "below_odds": p < 1 / float(odd),
    }  # fmt: skip


async def proposals(
    session: AsyncSession, redis: Redis, *, premium: bool, now: datetime | None = None
) -> dict[str, Any]:
    """Matchs ouverts (dans une fenêtre) et combinés du moteur par profil."""
    from footprono.predictions import live_chances

    now = now or datetime.now(UTC)
    published, source = await settings_of(session)
    out: dict[str, Any] = {"published": published, "odds_source": source, "matches": [],
                           "combos": {}, "open": 0, "trial": True}  # fmt: skip
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
    out["open"] = len(open_)
    if not open_:
        return out
    out["trial"] = await in_trial(session)
    for mid in await thin_nations(session, list(open_), now):
        del open_[mid]  # sélection nationale avec trop peu de matchs récents
    chances = await live_chances.current(session, list(open_))
    odds, _ = await usable_odds(session, await load_odds(redis, list(open_), now), now)
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
        # Combiné : sélections ajoutées tant que sa chance reste au moins 3 points au-dessus
        # de 1/cote totale.
        chosen: list[dict[str, Any]] = []
        for _, sel in options:
            if len(chosen) == COMBO_SIZE[profile]:
                break
            trial = [*chosen, sel]
            p = math.prod(x["probability"] for x in trial)
            if p >= 1 / float(combined_odds(Decimal(x["odds"]) for x in trial)) + EDGE:
                chosen = trial
        if not chosen:
            continue
        chance = math.prod(s["probability"] for s in chosen)
        total = combined_odds(Decimal(s["odds"]) for s in chosen)
        locked = profile in PREMIUM_PROFILES and not premium
        out["combos"][profile] = {
            "size": len(chosen),
            "probability": round(chance, 4),
            "odds": str(total),
            "implied": round(1 / float(total), 4),
            "below_odds": chance < 1 / float(total),
            "locked": locked,
            "selections": [] if locked else chosen,
        }
    return out


async def live_offer(
    session: AsyncSession, redis: Redis, match_id: int, key: str, now: datetime
) -> tuple[Decimal, float | None] | None:
    """Cote en direct et chance du moteur d'une sélection pour placer un pari pendant une
    fenêtre ; None si le match n'est pas dans une fenêtre, si le coupon en direct n'est
    pas publié ou si la cote n'est plus proposée. Refusé (``AppError``) si la cote a été
    relevée avant un but ou un carton rouge, ou juste après un but."""
    from footprono.predictions import live_chances

    published, _ = await settings_of(session)
    match = await session.get(Match, match_id)
    if not published or match is None or match.status is not MatchStatus.SCHEDULED:
        return None
    if window(match.api_status, match.live_minute) is None:
        return None
    loaded = await load_odds(redis, [match_id], now)
    usable, after_goal = await usable_odds(session, loaded, now)
    if match_id in after_goal:
        raise AppError(AFTER_GOAL, details={"match_id": match_id})
    quotes = usable.get(match_id, {}).get("odds") or {}
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


# ------------------------------------------------- Fiabilité (maquette D15)


async def record_proposals(session: AsyncSession, redis: Redis, now: datetime | None = None) -> int:
    """Enregistre les sélections proposées en ce moment (tous profils, comme pour un joueur
    Premium), la première fois seulement pour un match, un profil et un moment."""
    from sqlalchemy.dialects.postgresql import insert

    from footprono.bookmaker.smart_models import LiveCouponPick

    now = now or datetime.now(UTC)
    data = await proposals(session, redis, premium=True, now=now)
    rows = [
        {
            "match_id": m["match_id"], "profile": profile, "moment": m["moment"],
            "minute": m["minute"], "market": s["market"], "line": s["line"],
            "selection": s["selection"], "probability": s["probability"],
            "odds": Decimal(s["odds"]), "proposed_at": now,
        }
        for m in data["matches"]
        for profile, s in m["picks"].items()
        if "market" in s
    ]  # fmt: skip
    if not rows:
        return 0
    result = await session.execute(
        insert(LiveCouponPick)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["match_id", "profile", "moment"])
        .returning(LiveCouponPick.id)
    )
    added = len(result.all())
    await session.commit()
    return added


async def settle_picks(session: AsyncSession, now: datetime | None = None) -> int:
    """Règle les propositions dont le match est terminé (mêmes règles que les paris)."""
    from footprono.bookmaker import settlement
    from footprono.bookmaker.models import BetSelection
    from footprono.bookmaker.smart_models import LiveCouponPick

    now = now or datetime.now(UTC)
    picks = (
        await session.scalars(
            select(LiveCouponPick)
            .join(Match, Match.id == LiveCouponPick.match_id)
            .where(
                LiveCouponPick.result.is_(None),
                Match.status.in_((MatchStatus.FINISHED, MatchStatus.CANCELLED)),
            )
        )
    ).all()
    done = 0
    for pick in picks:
        probe = BetSelection(
            match_id=pick.match_id, market=pick.market, line=pick.line,
            selection=pick.selection, odds=pick.odds,
        )  # fmt: skip
        grade = await settlement.grade_selection(session, probe, now)
        if grade is None:
            continue
        pick.result, pick.settled_at = grade.result, now
        done += 1
    await session.commit()
    return done


_SCORE = {"win": 1.0, "half_win": 0.5, "half_loss": 0.0, "loss": 0.0}


async def reliability(session: AsyncSession) -> dict[str, Any]:
    """Par profil et par moment : chance annoncée en moyenne, part gagnée, nombre de
    sélections, et si l'écart tient dans deux erreurs types (sélections remboursées
    écartées). Rien tant qu'aucune proposition n'est réglée."""
    from footprono.bookmaker.smart_models import LiveCouponPick

    rows = (
        await session.execute(
            select(
                LiveCouponPick.profile, LiveCouponPick.moment,
                LiveCouponPick.probability, LiveCouponPick.result, LiveCouponPick.odds,
            ).where(LiveCouponPick.result.in_(tuple(_SCORE)))
        )
    ).tuples().all()  # fmt: skip
    groups: dict[tuple[str, str], list[tuple[float, float, float]]] = {}
    for profile, moment, p, result, odd in rows:
        r = result or "loss"
        groups.setdefault((profile, moment), []).append((p, _SCORE[r], _profit(r, odd)))
    out: dict[str, list[dict[str, Any]]] = {}
    for profile in HALF_TIME_PROFILES:
        for moment, _, _ in WINDOWS:
            items = groups.get((profile, moment))
            if not items:
                continue
            n = len(items)
            announced = sum(p for p, _, _ in items) / n
            won = sum(w for _, w, _ in items) / n
            margin = 2 * math.sqrt(sum(p * (1 - p) for p, _, _ in items)) / n
            profit = sum(g for _, _, g in items)
            out.setdefault(profile, []).append({
                "moment": moment, "count": n, "announced": round(announced, 4),
                "won": round(won, 4), "margin": round(margin, 4),
                "fair": abs(won - announced) <= margin,
                # Bilan d'une mise de 1 000 F sur chaque proposition réglée.
                "profit": round(profit), "yield": round(profit / (n * STAKE), 4),
            })  # fmt: skip
    profit = sum(g for items in groups.values() for _, _, g in items)
    return {
        "profiles": out, "total": len(rows), "stake": STAKE, "profit": round(profit),
        "trial": await in_trial(session), "trial_settled": TRIAL_SETTLED,
    }  # fmt: skip
