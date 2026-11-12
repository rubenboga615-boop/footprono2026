"""Notifications pendant les matchs d'un coupon (demande du fondateur du 12/11/2026,
docs/AUDIT_PROPOSITION_NOTIFICATIONS_DIRECT_2026-11-12.md, sections 2 et 3).

Branchées sur le règlement des paris (chaque minute pendant les matchs) :

- sélection validée (gagnée, y compris avant la fin du match) ;
- but qui change l'état d'une sélection (gagnante ↔ perdante pour l'instant) ;
- « tout se joue sur le dernier match » (une fois par pari) ;
- match reporté, ou pas commencé 30 minutes après l'heure prévue (une fois par match).

La sélection perdue, donc le coupon perdu, passe par la notification de règlement
(``settlement._notify_settled``), qui dit maintenant quelle sélection a perdu.

Règles : événements d'un même passage groupés en une notification par joueur ; jamais les
cartons, corners ou tirs (``live_grade`` ne juge que les buts) ; réglage du joueur
(``User.match_notifications``) ; silence de 23 h à 8 h (notification gardée dans
l'application, rien sur le téléphone) ; jamais de proposition de pari.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.accounts.models import User
from footprono.bookmaker.models import Bet, BetSelection
from footprono.football.models import Match, Team
from footprono.notifications import service as notifications
from footprono.notifications.models import Notification

KIND = "bet_live"
QUIET_FROM, QUIET_TO = 23, 8
LATE_AFTER = timedelta(minutes=30)
# Décalage horaire (heures) des pays des joueurs ; UTC par défaut (Côte d'Ivoire, Togo,
# Sénégal, Mali, Burkina Faso, Guinée…).
UTC_OFFSETS = {"BJ": 1, "CM": 1, "GA": 1, "CG": 1, "CD": 1, "NE": 1, "TD": 1, "CF": 1, "GQ": 1,
               "NG": 1, "DZ": 1, "TN": 1, "MA": 1, "FR": 1, "BE": 1, "RW": 2, "BI": 2}  # fmt: skip
WON = {"win", "half_win"}
LOST = {"loss", "half_loss"}


@dataclass
class Event:
    user_id: int
    type: str  # validated, changed, last_match, delayed
    text: str
    bet_id: int
    match_id: int | None = None


@dataclass
class Alerts:
    """Événements d'un passage du règlement, groupés par joueur à la fin."""

    events: list[Event] = field(default_factory=list)
    _names: dict[int, tuple[str, str]] = field(default_factory=dict)


# ------------------------------------------------------------------- libellés français


def _line(line: str) -> str:
    return line.replace(".", ",")


def _ou(sel: str, line: str, one: str = "but", many: str = "buts") -> str:
    try:
        n = float(line)
    except ValueError:
        n = 2
    word = one if n < 2 else many
    return f"{'plus' if sel == 'over' else 'moins'} de {_line(line)} {word}"


def selection_label(market: str, line: str, sel: str, home: str, away: str) -> str:
    """« plus de 1,5 but », « victoire de Bénin », « Chypre (+2) »… (comme l'application)."""
    side = {"home": home, "away": away, "draw": "nul"}
    if market == "1X2":
        return "match nul" if sel == "draw" else f"victoire de {side.get(sel, sel)}"
    if market == "DC":
        return {"1X": f"{home} ou nul", "X2": f"nul ou {away}", "12": f"{home} ou {away}"}.get(
            sel, sel
        )
    if market == "DNB":
        return f"{side.get(sel, sel)} (remboursé si nul)"
    if market in ("OU", "HT_OU"):
        return _ou(sel, line) + (" à la mi-temps" if market == "HT_OU" else "")
    if market in ("TEAM_OU_HOME", "TEAM_OU_AWAY"):
        return f"{_ou(sel, line)} de {home if market.endswith('HOME') else away}"
    if market in ("BTTS", "HT_BTTS"):
        text = "les deux équipes marquent" if sel == "yes" else "pas les deux équipes"
        return text + (" à la mi-temps" if market == "HT_BTTS" else "")
    if market == "CS":
        return "autre score" if sel == "other" else f"score exact {sel}"
    if market == "HT_1X2":
        return "nul à la mi-temps" if sel == "draw" else f"{side.get(sel, sel)} mène à la pause"
    if market in ("AH", "EH"):
        try:
            v = float(line)
        except ValueError:
            v = 0.0
        v = v if sel != "away" else -v
        sign = "+" if v > 0 else ""
        team = side.get(sel, sel)
        return f"{team} ({sign}{_line(f'{v:g}')})"
    stats = {"CORNERS": ("corner", "corners"), "CARDS": ("carton", "cartons"),
             "SHOTS": ("tir", "tirs"), "SOT": ("tir cadré", "tirs cadrés")}  # fmt: skip
    prefix = market.split("_")[0]
    if prefix in stats and "_OU" in market and sel in ("over", "under"):
        one, many = stats[prefix]
        team = (
            f" de {home}"
            if market.endswith("HOME")
            else f" de {away}"
            if market.endswith("AWAY")
            else ""
        )
        return _ou(sel, line, one, many) + team
    return "ta sélection"


async def _names(alerts: Alerts, session: AsyncSession, match: Match) -> tuple[str, str]:
    if match.id not in alerts._names:
        home = await session.get(Team, match.home_team_id)
        away = await session.get(Team, match.away_team_id)
        alerts._names[match.id] = (
            home.name if home else "Domicile",
            away.name if away else "Extérieur",
        )
    return alerts._names[match.id]


def _score(match: Match) -> tuple[int | None, int | None]:
    if match.home_goals is not None and match.away_goals is not None:
        return match.home_goals, match.away_goals
    return match.live_home_goals, match.live_away_goals


def _scoreline(match: Match, home: str, away: str) -> str:
    h, a = _score(match)
    return f"{home} - {away}" if h is None else f"{home} {h}-{a} {away}"


async def lost_detail(
    session: AsyncSession, selections: list[BetSelection], results: list[str | None]
) -> str | None:
    """« Bénin 3-1 Togo : « moins de 2,5 buts » est perdu. » pour la notification de perte."""
    alerts = Alerts()
    for s, r in zip(selections, results, strict=True):
        if r in LOST:
            match = await session.get(Match, s.match_id)
            if match is None:
                return None
            home, away = await _names(alerts, session, match)
            label = selection_label(s.market, s.line, s.selection, home, away)
            return f"{_scoreline(match, home, away)} : « {label} » est perdu."
    return None


# --------------------------------------------------------------------- détection


async def observe(
    alerts: Alerts,
    session: AsyncSession,
    bet: Bet,
    selections: list[BetSelection],
    grades: list[Any],
    before: Sequence[str | None],
    now: datetime,
) -> None:
    """Événements d'un pari encore ouvert après ce passage du règlement (``before`` : résultat
    de chaque sélection avant le passage)."""
    from footprono.bookmaker.settlement import live_grade
    from footprono.ingestion.sources.api_football import UNPLAYED_STATUSES

    total = len(selections)
    decided = [g for g in grades if g is not None]
    ok = sum(g.result in WON or g.result == "push" for g in decided)
    for s, g, was in zip(selections, grades, before, strict=True):
        match = await session.get(Match, s.match_id)
        if match is None:
            continue
        home, away = await _names(alerts, session, match)
        label = selection_label(s.market, s.line, s.selection, home, away)
        if g is not None:
            s.live_state = None
            if g.result in WON and was in (None, "pending"):
                progress = f" Ton coupon : {ok} sur {total}." if total > 1 else ""
                text = f"✅ « {label} » validé ({_scoreline(match, home, away)}).{progress}"
                alerts.events.append(Event(bet.user_id, "validated", text, bet.id, match.id))
            continue
        # Pas encore décidée : gagnante ou perdante si le match s'arrêtait maintenant.
        state = live_grade(match, s.market, s.line, s.selection) if match.api_status else None
        state = "win" if state in WON else "loss" if state in LOST else state
        previous, s.live_state = s.live_state, state
        if previous and state in ("win", "loss") and state != previous:
            minute = f"{match.live_minute}' " if match.live_minute else ""
            now_text = "gagnante" if state == "win" else "perdante"
            text = (
                f"⚽ {minute}{_scoreline(match, home, away)} : « {label} » est {now_text} "
                "pour l'instant."
            )
            alerts.events.append(Event(bet.user_id, "changed", text, bet.id, match.id))
        late = match.kickoff_at is not None and now - match.kickoff_at > LATE_AFTER
        if match.api_status in UNPLAYED_STATUSES:
            what = {"PST": "reporté", "CANC": "annulé", "ABD": "arrêté"}.get(
                match.api_status or "", "interrompu"
            )
            text = (
                f"{home} - {away} est {what} : ta sélection sera remboursée s'il n'est pas "
                "joué dans les 48 heures."
            )
            alerts.events.append(Event(bet.user_id, "delayed", text, bet.id, match.id))
        elif late and match.api_status in (None, "NS", "TBD") and match.live_minute is None:
            text = f"{home} - {away} n'a pas commencé : heure à confirmer."
            alerts.events.append(Event(bet.user_id, "delayed", text, bet.id, match.id))
    undecided = {s.match_id for s, g in zip(selections, grades, strict=True) if g is None}
    if total >= 2 and len(undecided) == 1 and all(g.result not in LOST for g in decided):
        match = await session.get(Match, next(iter(undecided)))
        if match is not None:
            home, away = await _names(alerts, session, match)
            when = (
                "en cours"
                if match.live_minute is not None
                else match.kickoff_at.astimezone(UTC).strftime("%H:%M")
                if match.kickoff_at
                else "heure à confirmer"
            )
            text = f"{ok} sur {total} validées : tout se joue sur {home} - {away} ({when})."
            alerts.events.append(Event(bet.user_id, "last_match", text, bet.id, match.id))


# ----------------------------------------------------------------------- envoi

_TITLES = {
    "validated": "✅ Sélection validée",
    "changed": "⚽ But dans ton coupon",
    "last_match": "Tout se joue sur le dernier match",
    "delayed": "Match pas encore commencé",
}
_ORDER = ("validated", "changed", "last_match", "delayed")


def quiet(country: str, now: datetime) -> bool:
    hour = (now.astimezone(UTC).hour + UTC_OFFSETS.get(country.upper(), 0)) % 24
    return hour >= QUIET_FROM or hour < QUIET_TO


async def emit(alerts: Alerts, session: AsyncSession, now: datetime) -> int:
    """Une notification par joueur pour ce passage ; renvoie leur nombre."""
    if not alerts.events:
        return 0
    users = {
        u.id: u
        for u in await session.scalars(
            select(User).where(User.id.in_({e.user_id for e in alerts.events}))
        )
    }
    # « Tout se joue » une fois par pari, retard ou report une fois par match et par joueur.
    sent: set[tuple[int, str, int | None, int | None]] = set()
    for note in await session.scalars(
        select(Notification).where(
            Notification.kind == KIND,
            Notification.user_id.in_(set(users)),
            Notification.created_at > now - timedelta(days=3),
        )
    ):
        for e in note.data.get("events", []):
            sent.add((note.user_id, e.get("type"), e.get("bet_id"), e.get("match_id")))
    by_user: dict[int, list[Event]] = {}
    for e in alerts.events:
        user = users.get(e.user_id)
        if user is None or user.match_notifications == "none":
            continue
        if user.match_notifications == "results" and e.type != "validated":
            continue
        if e.type == "last_match" and (e.user_id, e.type, e.bet_id, e.match_id) in sent:
            continue
        if e.type == "delayed" and any(
            k[0] == e.user_id and k[1] == "delayed" and k[3] == e.match_id for k in sent
        ):
            continue
        mine = by_user.setdefault(e.user_id, [])
        # Même événement pour deux paris (même match) : une seule ligne.
        if all(other.text != e.text for other in mine):
            mine.append(e)
        if e.type in ("last_match", "delayed"):
            sent.add((e.user_id, e.type, e.bet_id, e.match_id))
    for user_id, events in by_user.items():
        events.sort(key=lambda e: _ORDER.index(e.type))
        types = {e.type for e in events}
        validated = sum(e.type == "validated" for e in events)
        if types == {"validated"} and validated > 1:
            title = f"✅ {validated} sélections validées"
        elif len(types) == 1:
            title = _TITLES[events[0].type]
        else:
            title = "Tes matchs en cours"
        user = users[user_id]
        notifications.add(
            session, user_id, KIND, title, "\n".join(e.text for e in events),
            {
                "screen": "bookmaker",
                "bets": sorted({e.bet_id for e in events}),
                "events": [
                    {"type": e.type, "bet_id": e.bet_id, "match_id": e.match_id} for e in events
                ],
                # Silence de 23 h à 8 h : gardée dans l'application, rien sur le téléphone.
                "silent": quiet(user.country or "", now),
            },
        )  # fmt: skip
    return len(by_user)
