"""Contrôles de qualité des données en base.

Chaque contrôle produit des constats classés :
- ``error``   : donnée manquante ou incohérente qui fausserait le modèle ;
- ``warning`` : écart à surveiller (couverture partielle, marge anormale).
Les exceptions connues sont déclarées explicitement, jamais masquées.
"""

from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.ingestion.reference import INTERRUPTED_SEASONS

# Délai après lequel un match daté dans le passé et toujours « à venir » est signalé.
STALE_SCHEDULED_DAYS = 2

MIN_XG_COVERAGE = 0.98
MIN_ODDS_COVERAGE = 0.98
OVERROUND_RANGE = (1.0, 1.25)


@dataclass
class Finding:
    severity: str
    competition: str
    season: int
    check: str
    message: str


def current_season_start(today: date | None = None) -> int:
    """Année de début de la saison en cours (les championnats reprennent en juillet-août)."""
    today = today or date.today()
    return today.year if today.month >= 7 else today.year - 1


_SEASON_SUMMARY = text(
    """
    SELECT c.code, s.id AS season_id, s.start_year,
           count(m.id) AS n_matches,
           count(m.id) FILTER (WHERE m.status = 'finished') AS n_finished,
           count(m.id) FILTER (WHERE m.status = 'cancelled') AS n_cancelled,
           count(m.id) FILTER (WHERE m.status = 'scheduled' AND m.match_date < :stale_before)
               AS n_stale,
           count(DISTINCT m.home_team_id) AS n_home_teams,
           (SELECT count(*) FROM (
                SELECT home_team_id FROM matches WHERE season_id = s.id
                UNION SELECT away_team_id FROM matches WHERE season_id = s.id) t) AS n_teams,
           count(m.id) FILTER (WHERE m.status = 'finished' AND (
                m.home_goals_ht > m.home_goals OR m.away_goals_ht > m.away_goals)) AS n_bad_ht,
           count(m.id) FILTER (WHERE m.status = 'finished' AND (
                SELECT count(*) FROM match_advanced_stats a
                WHERE a.match_id = m.id AND a.source = 'understat') = 2) AS n_with_xg,
           count(m.id) FILTER (WHERE m.status = 'finished' AND EXISTS (
                SELECT 1 FROM match_odds o WHERE o.match_id = m.id AND o.market = '1X2'
                  AND o.timing = 'pre' AND o.bookmaker = 'B365')) AS n_with_odds
    FROM seasons s
    JOIN competitions c ON c.id = s.competition_id
    LEFT JOIN matches m ON m.season_id = s.id
    GROUP BY c.code, s.id, s.start_year
    ORDER BY c.code, s.start_year
    """
)

_UNBALANCED_TEAMS = text(
    """
    SELECT t.name, count(*) FILTER (WHERE m.home_team_id = t.id) AS home,
           count(*) FILTER (WHERE m.away_team_id = t.id) AS away
    FROM matches m JOIN teams t ON t.id IN (m.home_team_id, m.away_team_id)
    WHERE m.season_id = :sid
    GROUP BY t.name
    HAVING count(*) FILTER (WHERE m.home_team_id = t.id) <> :expected
        OR count(*) FILTER (WHERE m.away_team_id = t.id) <> :expected
    """
)

# Une équipe ne joue pas deux matchs de championnat à moins de deux jours d'écart.
_DOUBLE_MATCHES = text(
    """
    WITH tm AS (
        SELECT id, match_date, home_team_id AS team_id FROM matches
        WHERE season_id = :sid AND status <> 'cancelled'
        UNION ALL
        SELECT id, match_date, away_team_id FROM matches
        WHERE season_id = :sid AND status <> 'cancelled'
    )
    SELECT t.name, a.match_date, a.id, b.id
    FROM tm a JOIN tm b ON a.team_id = b.team_id AND a.id < b.id
        AND abs(a.match_date - b.match_date) <= 1
    JOIN teams t ON t.id = a.team_id
    ORDER BY a.match_date, t.name
    """
)

_OVERROUND_OUTLIERS = text(
    """
    SELECT count(*) FROM (
        SELECT o.match_id, sum(1 / o.price) AS overround
        FROM match_odds o JOIN matches m ON m.id = o.match_id
        WHERE m.season_id = :sid AND o.market = '1X2' AND o.timing = 'pre' AND o.bookmaker = 'B365'
        GROUP BY o.match_id HAVING count(*) = 3
    ) x WHERE overround < :low OR overround > :high
    """
)


async def run_quality_checks(session: AsyncSession, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    current = current_season_start(today)
    stale_before = today - timedelta(days=STALE_SCHEDULED_DAYS)
    findings: list[Finding] = []
    seasons: list[dict[str, Any]] = []

    for row in (await session.execute(_SEASON_SUMMARY, {"stale_before": stale_before})).mappings():
        code, year, sid = row["code"], row["start_year"], row["season_id"]
        n_teams, n_matches, n_finished = row["n_teams"], row["n_matches"], row["n_finished"]
        complete = year < current
        expected = n_teams * (n_teams - 1)
        xg_cov = row["n_with_xg"] / n_finished if n_finished else None
        odds_cov = row["n_with_odds"] / n_finished if n_finished else None
        seasons.append(
            {
                "competition": code,
                "season": year,
                "teams": n_teams,
                "matches": n_matches,
                "finished": n_finished,
                "cancelled": row["n_cancelled"],
                "expected_matches": expected,
                "xg_coverage": round(xg_cov, 4) if xg_cov is not None else None,
                "odds_coverage": round(odds_cov, 4) if odds_cov is not None else None,
            }
        )

        def add(
            severity: str, check: str, message: str, code: str = code, year: int = year
        ) -> None:
            findings.append(Finding(severity, code, year, check, message))

        if n_teams not in (18, 20):
            add("error", "equipes", f"{n_teams} équipes (18 ou 20 attendues)")
        if n_matches > expected:
            add("error", "matchs", f"{n_matches} matchs pour {expected} possibles")
        if complete:
            known = INTERRUPTED_SEASONS.get((code, year))
            if n_finished != expected:
                if known:
                    add("warning", "completude", f"{n_finished}/{expected} matchs joués — {known}")
                else:
                    add("error", "completude", f"{n_finished}/{expected} matchs joués")
            elif not known:
                unbalanced = (
                    await session.execute(_UNBALANCED_TEAMS, {"sid": sid, "expected": n_teams - 1})
                ).all()
                for name, home, away in unbalanced:
                    add("error", "equilibre", f"{name} : {home} à domicile, {away} à l'extérieur")
        if row["n_cancelled"] and (code, year) not in INTERRUPTED_SEASONS:
            add("error", "annulations", f"{row['n_cancelled']} matchs annulés hors saison arrêtée")
        if row["n_stale"]:
            add(
                "error" if complete else "warning",
                "a_venir_depasses",
                f"{row['n_stale']} matchs datés d'avant le {stale_before} toujours « à venir » "
                "(report non daté ou résultat manquant)",
            )
        for name, day, first, second in (
            await session.execute(_DOUBLE_MATCHES, {"sid": sid})
        ).all():
            add("error", "doublons", f"{name} : matchs {first} et {second} autour du {day}")
        if row["n_bad_ht"]:
            add("error", "scores", f"{row['n_bad_ht']} matchs avec un score mi-temps > score final")
        if xg_cov is not None and xg_cov < MIN_XG_COVERAGE:
            add("warning", "xg", f"xG disponibles pour {xg_cov:.1%} des matchs joués")
        if odds_cov is not None and odds_cov < MIN_ODDS_COVERAGE:
            add("warning", "cotes", f"cotes B365 pré-match pour {odds_cov:.1%} des matchs joués")
        outliers = await session.scalar(
            _OVERROUND_OUTLIERS, {"sid": sid, "low": OVERROUND_RANGE[0], "high": OVERROUND_RANGE[1]}
        )
        if outliers:
            add("warning", "marge", f"{outliers} matchs avec une marge B365 hors {OVERROUND_RANGE}")

    findings.sort(key=lambda f: (f.severity != "error", f.competition, f.season, f.check))
    errors = sum(f.severity == "error" for f in findings)
    warnings = sum(f.severity == "warning" for f in findings)
    return {
        "status": "error" if errors else ("warning" if warnings else "ok"),
        "errors": errors,
        "warnings": warnings,
        "current_season": current,
        "seasons": seasons,
        "findings": [asdict(f) for f in findings],
    }
