"""Étude des compositions et absences : indicateurs calculés avec les seuls matchs d'avant."""

from types import SimpleNamespace

from footprono.engine import absences


def _row(match: int, player: int, *, position: str, goals: int = 0, coach: int = 1) -> object:
    return SimpleNamespace(
        id=match, side="home", player_api_id=player, starter=True, position=position,
        minutes=90, goals=goals, assists=0, coach_api_id=coach, team=100,
    )  # fmt: skip


def test_two_regular_starters_missing_and_new_coach() -> None:
    rows = []
    for m in range(8):
        coach = 1 if m < 6 else 2
        for pid in range(1, 12):
            if m == 7 and pid in (9, 10):  # deux habituels absents au 8e match
                continue
            rows.append(
                _row(m, pid, position="F" if pid > 8 else "D", goals=int(pid == 9), coach=coach)
            )
        if m == 7:
            rows += [_row(m, 20, position="F", coach=2), _row(m, 21, position="F", coach=2)]
    feats = absences.features(rows)
    assert (5, "home") in feats  # 5 matchs d'historique : premier calcul
    assert feats[(5, "home")] == {
        "manque": 0.0, "manque_attaque": 0.0, "manque_defense": 0.0, "nouvel_entraineur": 0.0,
    }  # fmt: skip
    eighth = feats[(7, "home")]
    assert eighth["manque"] == 2 / 11
    assert eighth["manque_attaque"] == 1.0  # le seul buteur est absent
    assert eighth["manque_defense"] == 0.0
    assert eighth["nouvel_entraineur"] == 1.0
    assert (4, "home") not in feats  # moins de 5 matchs d'historique
