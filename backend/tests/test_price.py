"""Moteur 2 (moteur 3.0) : prix d'une sélection, calage d'un match, choix des paris bien payés."""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from footprono.bookmaker import price, service, smart_coupon
from footprono.engine.markets import derive_markets
from footprono.engine.scores import score_distribution
from footprono.predictions.calibration import calibrate


@pytest.mark.parametrize(
    ("probability", "odds", "expected"),
    [
        (0.62, "1.60", price.GOOD),  # 0,992
        (0.60, "1.60", price.NEUTRAL),  # 0,96
        (0.55, "1.60", price.EXPENSIVE),  # 0,88
        (0.70, "1.60", price.SUSPECT),  # 1,12 : cote qui n'a pas suivi le marché
    ],
)
def test_price_tiers(probability: float, odds: str, expected: int) -> None:
    assert price.tier(probability, Decimal(odds), priced=True) == expected


def test_price_is_neutral_without_reference() -> None:
    # Match non calé, ou marché de corners / tirs : le prix n'a pas de sens.
    assert price.tier(0.55, Decimal("1.60"), priced=False) == price.NEUTRAL
    assert price.tier(0.70, Decimal("1.60"), priced=False) == price.NEUTRAL


def test_is_priced_needs_calibration_and_a_goal_market() -> None:
    calibrated = {"1X2||home": 0.5, service.CALIBRATED_KEY: 1.0}
    assert service.is_priced(calibrated, "1X2")
    assert service.is_priced(calibrated, "TEAM_OU_HOME")
    assert not service.is_priced(calibrated, "CORNERS_OU")
    assert not service.is_priced(calibrated, "SOT_OU")
    assert not service.is_priced({"1X2||home": 0.5}, "1X2")


def _engine_markets(lam_h: float, lam_a: float) -> dict[str, list[float]]:
    dist = score_distribution(lam_h, lam_a, -0.05, 0.45, 0.45)
    out = {k: [s.win, s.half_win, s.push, s.half_loss] for k, s in derive_markets(dist).items()}
    out["CORNERS_OU|9.5|over"] = [0.52, 0.0, 0.0, 0.0]
    return out


def test_calibrate_follows_the_reference_and_keeps_markets_coherent() -> None:
    markets = _engine_markets(1.3, 1.3)  # le moteur voit un match équilibré
    reference = {
        "1X2||home": 1.45, "1X2||draw": 4.60, "1X2||away": 7.50,
        "OU|2.5|over": 1.80, "OU|2.5|under": 2.05,
    }  # fmt: skip
    cal = calibrate(1.3, 1.3, -0.05, 0.45, 0.45, markets, reference)
    assert cal.calibrated
    p = cal.probabilities
    assert p["1X2||home"] == pytest.approx(0.66, abs=0.03)
    assert p["1X2||home"] > 2 * p["1X2||away"]
    # Tous les marchés de buts sortent de la même loi : cohérence exacte.
    assert p["1X2||home"] + p["1X2||draw"] + p["1X2||away"] == pytest.approx(1.0, abs=1e-9)
    assert p["DC||1X"] == pytest.approx(p["1X2||home"] + p["1X2||draw"], abs=1e-9)
    assert p["OU|2.5|over"] + p["OU|2.5|under"] == pytest.approx(1.0, abs=1e-9)
    assert p["OU|1.5|over"] > p["OU|2.5|over"] > p["OU|3.5|over"]
    # Mêmes clés que le moteur, et les corners gardent sa probabilité.
    assert set(p) == set(markets)
    assert p["CORNERS_OU|9.5|over"] == 0.52


@pytest.mark.parametrize(
    "reference",
    [
        {},
        {"1X2||home": 1.45, "1X2||draw": 4.60},  # 1-N-2 incomplet
        {"1X2||home": 2.60, "1X2||draw": 3.60, "1X2||away": 3.10},  # pas de marge
    ],
)
def test_calibrate_falls_back_to_the_engine(reference: dict[str, float]) -> None:
    markets = _engine_markets(1.6, 1.1)
    cal = calibrate(1.6, 1.1, -0.05, 0.45, 0.45, markets, reference)
    assert not cal.calibrated
    assert (cal.lambda_home, cal.lambda_away) == (1.6, 1.1)
    assert cal.probabilities["1X2||home"] == pytest.approx(markets["1X2||home"][0])


def _pick(p: float, tier: int) -> smart_coupon.Pick:
    return smart_coupon.Pick(SimpleNamespace(), "A", "B", "EPL", SimpleNamespace(), p, tier)  # type: ignore[arg-type]


def test_coupon_angle_prefers_well_priced_selections() -> None:
    profile = smart_coupon.PROFILES["equilibre"]
    # La plus probable est chère : on prend la plus probable des bien payées.
    inside = [_pick(0.74, price.EXPENSIVE), _pick(0.70, price.GOOD), _pick(0.66, price.GOOD)]
    assert smart_coupon.choose(profile, inside).probability == 0.70
    # Une cote suspecte n'est prise que s'il n'y a rien d'autre.
    assert smart_coupon.choose(profile, [_pick(0.74, price.SUSPECT), _pick(0.61, price.EXPENSIVE)])
    assert (
        smart_coupon.choose(
            profile, [_pick(0.74, price.SUSPECT), _pick(0.61, price.EXPENSIVE)]
        ).probability
        == 0.61
    )
