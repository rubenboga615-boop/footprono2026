"""Chances en direct : vérification sur les matchs joués et calcul pendant un match (plan du
10/11/2026, étape 6). Moteur : ``engine/live.py`` ; règle de justesse : ``engine/live_study``.

Rien n'est montré aux joueurs tant que la console n'a pas publié les chances en direct
(Moteur → « Chances en direct publiées »), après une vérification juste.
"""

from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.engine.live import LIVE_STATUSES, LiveState, live_markets
from footprono.engine.live_study import PlayedMatch, consistent, minute_entries, report
from footprono.football.models import LiveSnapshot, Match, MatchEvent, MatchStatus
from footprono.predictions.models import MatchPrediction, PredictionRun

# Marchés montrés pendant le match (les autres restent calculés pour les paris en cours).
SHOWN = ("1X2||home", "1X2||draw", "1X2||away", "OU|2.5|over", "BTTS||yes")


def _goal(detail: str | None) -> bool:
    return (detail or "") != "Missed Penalty"


def _red(detail: str | None) -> bool:
    d = (detail or "").lower()
    return "red" in d or "second yellow" in d


# Numéros de matchs par requête : PostgreSQL refuse plus de 32 767 paramètres (console du
# 11/11/2026 : « Vérifier les chances en direct » sur 50 000 matchs).
CHUNK = 5000


def _chunks(ids: Sequence[int]) -> list[list[int]]:
    ids = list(ids)
    return [ids[i : i + CHUNK] for i in range(0, len(ids), CHUNK)]


async def _prematch(
    session: AsyncSession, match_ids: Sequence[int]
) -> dict[int, tuple[float, float, float, float]]:
    """Dernière prévision d'avant-match (calculée avant le coup d'envoi) de chaque match."""
    out: dict[int, tuple[float, float, float, float]] = {}
    for chunk in _chunks(match_ids):
        out.update(await _prematch_chunk(session, chunk))
    return out


async def _prematch_chunk(
    session: AsyncSession, match_ids: list[int]
) -> dict[int, tuple[float, float, float, float]]:
    rows = await session.execute(
        select(
            MatchPrediction.match_id,
            MatchPrediction.lambda_home,
            MatchPrediction.lambda_away,
            MatchPrediction.share_home,
            MatchPrediction.share_away,
        )
        .join(PredictionRun, PredictionRun.id == MatchPrediction.run_id)
        .join(Match, Match.id == MatchPrediction.match_id)
        .where(
            MatchPrediction.match_id.in_(match_ids),
            PredictionRun.as_of <= Match.match_date,
        )
        .order_by(MatchPrediction.match_id, MatchPrediction.run_id.desc())
        .distinct(MatchPrediction.match_id)
    )
    return {r[0]: (r[1], r[2], r[3], r[4]) for r in rows.tuples()}


async def _events(session: AsyncSession, match_ids: Sequence[int]) -> dict[int, list[MatchEvent]]:
    out: dict[int, list[MatchEvent]] = defaultdict(list)
    for chunk in _chunks(match_ids):
        for e in await session.scalars(
            select(MatchEvent)
            .where(MatchEvent.match_id.in_(chunk), MatchEvent.kind.in_(("Goal", "Card")))
            .order_by(MatchEvent.match_id, MatchEvent.seq)
        ):
            out[e.match_id].append(e)
    return out


def played_match(
    params: tuple[float, float, float, float],
    events: Sequence[MatchEvent],
    final: tuple[int, int, int, int],
) -> PlayedMatch | None:
    """Match pour l'étude. Le camp d'un but contre son camp n'a pas la même convention
    partout : celle qui redonne le score final est gardée, sinon le match est écarté."""
    reds = tuple(
        (e.minute or 0, e.extra or 0, e.side or "")
        for e in events
        if e.kind == "Card" and _red(e.detail)
    )
    goals = [e for e in events if e.kind == "Goal" and _goal(e.detail) and e.side]
    for flip in (False, True):
        sides = []
        for e in goals:
            side = e.side or ""
            if flip and e.detail == "Own Goal":
                side = "away" if side == "home" else "home"
            sides.append((e.minute or 0, e.extra or 0, side))
        m = PlayedMatch(params, tuple(sides), reds, final)
        if consistent(m):
            return m
    return None


async def study(session: AsyncSession) -> dict[str, Any]:
    """Repères 15', 30', 60', 75' sur les matchs terminés dont les événements sont gardés et
    qui avaient une prévision d'avant-match."""
    with_details = select(LiveSnapshot.id).where(LiveSnapshot.match_id == Match.id).exists()
    rows = (
        await session.execute(
            select(
                Match.id, Match.home_goals, Match.away_goals,
                Match.home_goals_ht, Match.away_goals_ht,
            ).where(Match.status == MatchStatus.FINISHED, with_details)
        )
    ).tuples().all()  # fmt: skip
    ids = [r[0] for r in rows]
    prematch = await _prematch(session, ids)
    events = await _events(session, [i for i in ids if i in prematch])
    matches, skipped = [], 0
    for mid, hg, ag, hht, aht in rows:
        if mid not in prematch or hg is None or ag is None or hht is None or aht is None:
            continue
        m = played_match(prematch[mid], events.get(mid, []), (hg, ag, hht, aht))
        if m is None:
            skipped += 1
        else:
            matches.append(m)
    out = report(minute_entries(matches))
    out["matches"] = len(matches)
    out["inconsistent"] = skipped
    return out


async def current(session: AsyncSession, match_ids: Sequence[int]) -> dict[int, dict[str, Any]]:
    """Chances du moment des matchs en cours : dernier relevé, cartons rouges, prévision
    d'avant-match. Un match absent : pas de chance calculable (carton rouge, prolongation…)."""
    if not match_ids:
        return {}
    snaps = {
        s.match_id: s
        for s in await session.scalars(
            select(LiveSnapshot)
            .where(LiveSnapshot.match_id.in_(list(match_ids)))
            .order_by(LiveSnapshot.match_id, LiveSnapshot.taken_at.desc())
            .distinct(LiveSnapshot.match_id)
        )
    }
    live = [i for i, s in snaps.items() if s.status in LIVE_STATUSES]
    prematch = await _prematch(session, live)
    events = await _events(session, live)
    ht = {
        m.id: (m.home_goals_ht, m.away_goals_ht)
        for m in await session.scalars(select(Match).where(Match.id.in_(live)))
    }
    out: dict[int, dict[str, Any]] = {}
    for mid in live:
        s = snaps[mid]
        if mid not in prematch or s.home_goals is None or s.away_goals is None:
            continue
        reds = [e for e in events.get(mid, []) if e.kind == "Card" and _red(e.detail)]
        hh, ha = ht.get(mid, (None, None))
        state = LiveState(
            s.status, s.minute, s.extra, s.home_goals, s.away_goals, hh, ha,
            red_home=sum(e.side == "home" for e in reds),
            red_away=sum(e.side == "away" for e in reds),
        )  # fmt: skip
        markets = live_markets(*prematch[mid], state)
        if markets is None:
            continue
        out[mid] = {
            "status": s.status,
            "minute": s.minute,
            "extra": s.extra,
            "taken_at": s.taken_at.astimezone(UTC).isoformat(),
            "markets": {k: round(sel.win, 4) for k, sel in markets.items()},
        }
    return out
