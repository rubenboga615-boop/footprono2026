"""Rappel de coup d'envoi : « Ton pari commence dans 25 min : Leeds - Tottenham ».

Revue du 07/11/2026 : l'application ne parlait au joueur que quand il perdait. Une fois par
pari en cours, quand son premier match commence dans 30 minutes au plus ; les paris d'un même
joueur qui commencent dans la même fenêtre sont groupés en une seule notification. Une
information, jamais une invitation à parier davantage.
"""

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from footprono.bookmaker.models import Bet, BetSelection
from footprono.football.models import Match, Team
from footprono.notifications import service as notifications
from footprono.notifications.models import Notification

KIND = "bet_kickoff"
BEFORE = timedelta(minutes=30)


async def send_kickoff_reminders(session: AsyncSession, now: datetime | None = None) -> int:
    """Crée les rappels des paris dont le premier match commence bientôt ; renvoie leur
    nombre (un par joueur). Un pari déjà rappelé ne l'est plus."""
    now = now or datetime.now(UTC)
    first = (
        select(BetSelection.bet_id, func.min(Match.kickoff_at).label("kickoff"))
        .join(Match, Match.id == BetSelection.match_id)
        .join(Bet, Bet.id == BetSelection.bet_id)
        .where(Bet.status == "open")
        .group_by(BetSelection.bet_id)
        .subquery()
    )
    rows = (
        await session.execute(
            select(Bet.id, Bet.user_id, first.c.kickoff)
            .join(first, first.c.bet_id == Bet.id)
            .where(
                first.c.kickoff > now,
                first.c.kickoff <= now + BEFORE,
                # Pari placé juste avant le match : le joueur le sait déjà.
                Bet.placed_at <= first.c.kickoff - BEFORE,
            )
        )
    ).all()
    if not rows:
        return 0
    done = {
        int(b)
        for data in await session.scalars(
            select(Notification.data).where(
                Notification.kind == KIND,
                Notification.user_id.in_({r.user_id for r in rows}),
                Notification.created_at > now - timedelta(days=2),
            )
        )
        for b in data.get("bets", [])
    }
    by_user: dict[int, list[tuple[int, datetime]]] = defaultdict(list)
    for bet_id, user_id, kickoff in rows:
        if bet_id not in done:
            by_user[user_id].append((bet_id, kickoff))
    for user_id, bets in by_user.items():
        bets.sort(key=lambda b: b[1])
        # Chaque match qui commence, pas seulement le premier (12/11/2026 : « 2 de tes paris
        # commencent bientôt — Arménie - Chypre… », Turquie - Belgique manquait).
        starts: dict[str, int] = {}
        for bet_id, kickoff in bets:
            label = await _first_match(session, bet_id, kickoff)
            starts.setdefault(label, max(1, round((kickoff - now).total_seconds() / 60)))
        title = (
            f"Ton pari commence dans {next(iter(starts.values()))} min"
            if len(bets) == 1
            else f"{len(bets)} de tes paris commencent bientôt"
        )
        notifications.add(
            session, user_id, KIND, title,
            f"{_starts_text(starts)} Suivi en direct dans Mes paris.",
            {"bets": [b for b, _ in bets], "screen": "bookmaker"},
        )  # fmt: skip
    await session.commit()
    return len(by_user)


def _starts_text(starts: dict[str, int]) -> str:
    """« Arménie - Chypre commence dans 30 min. » ; plusieurs matchs : « Arménie - Chypre dans
    30 min, Turquie - Belgique dans 30 min. » (3 au plus, puis « et 2 autres matchs »)."""
    items = list(starts.items())
    if len(items) == 1:
        label, minutes = items[0]
        return f"{label} commence dans {minutes} min."
    shown = ", ".join(f"{label} dans {m} min" for label, m in items[:3])
    rest = len(items) - 3
    return (
        shown
        + (
            f" et {rest} autre{'s' if rest > 1 else ''} match{'s' if rest > 1 else ''}"
            if rest > 0
            else ""
        )
        + "."
    )


async def _first_match(session: AsyncSession, bet_id: int, kickoff: datetime) -> str:
    home, away = aliased(Team), aliased(Team)
    names = (
        await session.execute(
            select(home.name, away.name)
            .select_from(BetSelection)
            .join(Match, Match.id == BetSelection.match_id)
            .join(home, home.id == Match.home_team_id)
            .join(away, away.id == Match.away_team_id)
            .where(BetSelection.bet_id == bet_id, Match.kickoff_at == kickoff)
            .limit(1)
        )
    ).first()
    return f"{names[0]} - {names[1]}" if names else "Le premier match"
