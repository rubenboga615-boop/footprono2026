"""Audit de tous les marchés : familles, référence causale, verdicts."""

from footprono.engine.audit import audit_report, family_of, format_audit, goal_entries, goal_history

from .test_calibration import COMPS, _world


def test_families_cover_goal_and_count_markets() -> None:
    assert family_of("OU|2.5|over") == "Buts du match (plus/moins)"
    assert family_of("TEAM_OU_AWAY|1.5|under") == "Buts d'une équipe"
    assert family_of("HTFT||home/draw") == "Mi-temps / fin de match"
    assert family_of("CORNERS_TEAM_OU_HOME|4.5|over") == "Corners : par équipe"
    assert family_of("CARDS_1X2||home") == "Cartons : le plus de"
    assert family_of("SOT_OU|8.5|over") == "Tirs cadrés : total"


def test_exact_engine_has_nothing_to_correct() -> None:
    # Environ 200 tranches testées : une fausse alerte reste possible avec certains
    # tirages (c'est le cas de la graine 5) ; graine fixée sans hasard extrême.
    hist, pred = _world(250, None, 7)
    entries = goal_entries(hist, pred)
    keys = {e.key for e in entries}
    assert "CS||1-0" in keys
    assert "AH|-0.5|home" in keys
    assert not any(k.startswith(("AH|-1|", "AH|-0.25|", "DNB|")) for k in keys)  # remboursements
    report = audit_report(entries, goal_history(hist, COMPS, [2022, 2023, 2024]))
    verdicts = {f: m["verdict"] for f, m in report["families"].items()}
    assert "à corriger" not in verdicts.values(), verdicts
    assert verdicts["Résultat (1X2)"] == "validé"


def test_biased_engine_is_sent_back_for_correction() -> None:
    hist, pred = _world(250, None, 5)
    pred.lam_h = [x * 1.35 for x in pred.lam_h]
    pred.lam_a = [x * 1.35 for x in pred.lam_a]
    report = audit_report(goal_entries(hist, pred), goal_history(hist, COMPS, [2022, 2023, 2024]))
    ou = report["families"]["Buts du match (plus/moins)"]
    assert ou["verdict"] in {"à corriger", "sans apport"}
    assert ou["worst_bin"] is not None or ou["verdict"] == "sans apport"
    assert "Buts du match" in format_audit(report)
