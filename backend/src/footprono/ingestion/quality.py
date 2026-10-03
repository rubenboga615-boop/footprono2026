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

from footprono.ingestion.reference import (
    AWARDED_MATCHES,
    COMPETITIONS_BY_CODE,
    INTERRUPTED_SEASONS,
)

# Délai après lequel un match daté dans le passé et toujours « à venir » est signalé.
STALE_SCHEDULED_DAYS = 2

MIN_XG_COVERAGE = 0.98
MIN_ODDS_COVERAGE = 0.98
MIN_API_STATS_COVERAGE = 0.98
MIN_CORNER_AGREEMENT = 0.95
MAX_HALF_MISMATCH_RATE = 0.01
# Saisons pour lesquelles API-Football fournit les statistiques par mi-temps.
API_STATS_FIRST_SEASON = 2024
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
           count(m.id) FILTER (WHERE m.leg > 1) AS n_repeated,
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
                  AND o.timing = 'pre' AND o.bookmaker = 'B365')) AS n_with_odds,
           count(m.id) FILTER (WHERE m.status = 'finished' AND EXISTS (
                SELECT 1 FROM match_team_stats t WHERE t.match_id = m.id
                  AND t.source = 'api_football' AND t.period = 'full')) AS n_with_api_stats,
           count(m.id) FILTER (WHERE m.status = 'finished' AND EXISTS (
                SELECT 1 FROM match_team_stats t WHERE t.match_id = m.id
                  AND t.source = 'api_football' AND t.period = 'first_half')) AS n_with_api_halves
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

_FIXTURE_NAMES = text(
    """
    SELECT m.id, th.name, ta.name FROM matches m
    JOIN teams th ON th.id = m.home_team_id JOIN teams ta ON ta.id = m.away_team_id
    WHERE m.id = ANY(:ids)
    """
)

# Mi-temps incohérentes : 1re + 2e période ≠ match complet (corners, cartons jaunes).
_HALF_MISMATCHES = text(
    """
    SELECT count(*) FROM match_team_stats f
    JOIN match_team_stats h1 ON h1.match_id = f.match_id AND h1.team_id = f.team_id
        AND h1.source = f.source AND h1.period = 'first_half'
    JOIN match_team_stats h2 ON h2.match_id = f.match_id AND h2.team_id = f.team_id
        AND h2.source = f.source AND h2.period = 'second_half'
    JOIN matches m ON m.id = f.match_id
    WHERE m.season_id = :sid AND f.source = 'api_football' AND f.period = 'full'
      AND (f.corners <> h1.corners + h2.corners
           OR f.yellow_cards <> h1.yellow_cards + h2.yellow_cards)
    """
)

# Accord des corners entre API-Football et football-data (équipe à domicile).
_CORNER_AGREEMENT = text(
    """
    SELECT count(*) AS n, count(*) FILTER (WHERE t.corners = m.home_corners) AS same
    FROM match_team_stats t JOIN matches m ON m.id = t.match_id
    WHERE m.season_id = :sid AND t.source = 'api_football' AND t.period = 'full'
      AND t.team_id = m.home_team_id AND m.home_corners IS NOT NULL
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

        ref = COMPETITIONS_BY_CODE.get(code)
        counts = ref.team_counts if ref else (18, 20)
        if n_teams not in counts:
            allowed = " ou ".join(str(n) for n in counts)
            add("error", "equipes", f"{n_teams} équipes ({allowed} attendues)")
        # Phase finale (Belgique) : plus de matchs qu'un aller-retour, calendrier non
        # équilibré ; le nombre de matchs et l'équilibre ne se contrôlent pas ainsi.
        playoffs = ref is not None and ref.playoffs
        if n_matches > expected and not playoffs:
            add("error", "matchs", f"{n_matches} matchs pour {expected} possibles")
        if complete and playoffs:
            if n_finished < expected and (code, year) not in INTERRUPTED_SEASONS:
                add("error", "completude", f"{n_finished} matchs joués, moins qu'un aller-retour")
        elif complete:
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
        if row["n_repeated"] and not playoffs:
            add("error", "affiches", f"{row['n_repeated']} affiches jouées plus d'une fois")
        if row["n_cancelled"] and (code, year) not in INTERRUPTED_SEASONS:
            add("error", "annulations", f"{row['n_cancelled']} matchs annulés hors saison arrêtée")
        if row["n_stale"]:
            add(
                "error" if complete else "warning",
                "a_venir_depasses",
                f"{row['n_stale']} matchs datés d'avant le {stale_before} toujours « à venir » "
                "(report non daté ou résultat manquant)",
            )
        doubles = (await session.execute(_DOUBLE_MATCHES, {"sid": sid})).all()
        # Un match donné sur tapis vert (jamais joué) peut tomber à côté d'un vrai match.
        fixtures = (
            {
                mid: (code, year, home, away)
                for mid, home, away in (
                    await session.execute(
                        _FIXTURE_NAMES, {"ids": [d[2] for d in doubles] + [d[3] for d in doubles]}
                    )
                ).tuples()
            }
            if doubles
            else {}
        )
        for name, day, first, second in doubles:
            if fixtures.get(first) in AWARDED_MATCHES or fixtures.get(second) in AWARDED_MATCHES:
                continue
            add("error", "doublons", f"{name} : matchs {first} et {second} autour du {day}")
        if row["n_bad_ht"]:
            add("error", "scores", f"{row['n_bad_ht']} matchs avec un score mi-temps > score final")
        if xg_cov is not None and xg_cov < MIN_XG_COVERAGE and (ref is None or ref.understat_slug):
            add("warning", "xg", f"xG disponibles pour {xg_cov:.1%} des matchs joués")
        if odds_cov is not None and odds_cov < MIN_ODDS_COVERAGE:
            add("warning", "cotes", f"cotes B365 pré-match pour {odds_cov:.1%} des matchs joués")
        if year >= API_STATS_FIRST_SEASON and n_finished:
            api_cov = row["n_with_api_stats"] / n_finished
            half_cov = row["n_with_api_halves"] / n_finished
            seasons[-1]["api_stats_coverage"] = round(api_cov, 4)
            seasons[-1]["api_halves_coverage"] = round(half_cov, 4)
            if api_cov < MIN_API_STATS_COVERAGE:
                add(
                    "warning",
                    "stats_api",
                    f"stats API-Football pour {api_cov:.1%} des matchs joués",
                )
            elif half_cov < MIN_API_STATS_COVERAGE:
                add(
                    "warning", "stats_api", f"découpage par mi-temps pour {half_cov:.1%} des matchs"
                )
            if row["n_with_api_halves"]:
                mismatches = await session.scalar(_HALF_MISMATCHES, {"sid": sid}) or 0
                if mismatches > MAX_HALF_MISMATCH_RATE * 2 * row["n_with_api_halves"]:
                    add("warning", "mi_temps", f"{mismatches} lignes où 1re + 2e mi-temps ≠ match")
            agreement = (await session.execute(_CORNER_AGREEMENT, {"sid": sid})).one()
            if agreement.n and agreement.same / agreement.n < MIN_CORNER_AGREEMENT:
                add(
                    "warning",
                    "corners",
                    f"corners API-Football = football-data pour {agreement.same / agreement.n:.1%}"
                    " des matchs seulement",
                )
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
