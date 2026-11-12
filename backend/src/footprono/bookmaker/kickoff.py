"""Rappel de coup d'envoi : « ⏰ Dans 25 min : Leeds - Tottenham (ton coupon n° 57) ».

Revue du 07/11/2026 : l'application ne parlait au joueur que quand il perdait. Retour du
testeur du 12/11/2026 : un seul rappel par pari (son premier match) ne suffisait pas ; un
rappel 30 minutes avant **chaque** match d'un pari en cours, une fois par match et par joueur.
Les matchs d'un même joueur qui commencent dans la même fenêtre sont cités dans une seule
notification. Pas de rappel pour un pari placé moins de 30 minutes avant le match (le joueur
le sait déjà ; « C'est parti » au coup d'envoi part quand même, voir live_alerts.py).
Une information, jamais une invitation à parier davantage.
"""

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.accounts.models import User
from footprono.bookmaker.live_alerts import quiet
from footprono.bookmaker.models import Bet, BetSelection
from footprono.football.models import Match, Team
from footprono.notifications import service as notifications
from footprono.notifications.models import Notification

KIND = "bet_kickoff"
BEFORE = timedelta(minutes=30)


async def send_kickoff_reminders(session: AsyncSession, now: datetime | None = None) -> int:
    """Crée les rappels des matchs de paris en cours qui commencent bientôt ; renvoie leur
    nombre (un par joueur). Un match déjà rappelé à un joueur ne l'est plus."""
    now = now or datetime.now(UTC)
    rows = (
        await session.execute(
            select(Bet.id, Bet.user_id, Match.id, Match.kickoff_at)
            .join(BetSelection, BetSelection.bet_id == Bet.id)
            .join(Match, Match.id == BetSelection.match_id)
            .where(
                Bet.status == "open",
                Match.kickoff_at > now,
                Match.kickoff_at <= now + BEFORE,
                # Pari placé juste avant le match : le joueur le sait déjà.
                Bet.placed_at <= Match.kickoff_at - BEFORE,
            )
        )
    ).all()
    if not rows:
        return 0
    users = {r[1] for r in rows}
    done: set[tuple[int, int]] = set()
    old_bets: set[int] = set()
    for note in await session.scalars(
        select(Notification).where(
            Notification.kind == KIND,
            Notification.user_id.in_(users),
            Notification.created_at > now - timedelta(days=2),
        )
    ):
        done |= {(note.user_id, int(m)) for m in note.data.get("matches", [])}
        if "matches" not in note.data:  # rappels d'avant le 13/11 : par pari
            old_bets |= {int(b) for b in note.data.get("bets", [])}
    # Matchs à rappeler, par joueur : heure et paris concernés.
    todo: dict[int, dict[int, tuple[datetime, set[int]]]] = defaultdict(dict)
    for bet_id, user_id, match_id, kickoff in rows:
        if (user_id, match_id) in done or bet_id in old_bets:
            continue
        _, bets = todo[user_id].setdefault(match_id, (kickoff, set()))
        bets.add(bet_id)
    countries = {
        u.id: u.country or ""
        for u in await session.scalars(select(User).where(User.id.in_(set(todo))))
    }
    for user_id, matches in todo.items():
        ordered = sorted(matches.items(), key=lambda kv: kv[1][0])
        lines = []
        for match_id, (kickoff, bets) in ordered:
            minutes = max(1, round((kickoff - now).total_seconds() / 60))
            lines.append(
                f"⏰ Dans {minutes} min : {await _match_name(session, match_id)} "
                f"({await _coupons(session, sorted(bets))})."
            )
        title = (
            "⏰ Ton match commence bientôt"
            if len(ordered) == 1
            else f"⏰ {len(ordered)} de tes matchs commencent bientôt"
        )
        all_bets = sorted({b for _, (_, bets) in ordered for b in bets})
        notifications.add(
            session, user_id, KIND, title,
            "\n".join(lines) + " Suivi en direct dans Mes paris.",
            {
                "bets": all_bets, "matches": [m for m, _ in ordered], "screen": "bookmaker",
                **({"bet_id": all_bets[0]} if len(all_bets) == 1 else {}),
                "silent": quiet(countries.get(user_id, ""), now),
            },
        )  # fmt: skip
    await session.commit()
    return len(todo)


async def _coupons(session: AsyncSession, bet_ids: list[int]) -> str:
    """« ton coupon n° 57, 1 sur 3 validée » ; plusieurs : « tes coupons n° 57 et 60 »."""
    if len(bet_ids) > 1:
        return "tes coupons n° " + ", ".join(map(str, bet_ids[:-1])) + f" et {bet_ids[-1]}"
    results = list(
        await session.scalars(select(BetSelection.result).where(BetSelection.bet_id == bet_ids[0]))
    )
    if len(results) < 2:
        return f"ton pari n° {bet_ids[0]}"
    ok = sum(r in ("win", "half_win", "push") for r in results)
    return f"ton coupon n° {bet_ids[0]}, {ok} sur {len(results)} validée{'s' if ok > 1 else ''}"


async def _match_name(session: AsyncSession, match_id: int) -> str:
    match = await session.get(Match, match_id)
    if match is None:
        return "ton match"
    home = await session.get(Team, match.home_team_id)
    away = await session.get(Team, match.away_team_id)
    return f"{home.name if home else 'Domicile'} - {away.name if away else 'Extérieur'}"
