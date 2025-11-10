import math

from tts_irt import irt_prob, item_information


def approx(a, b, rel=1e-6):
    return abs(a - b) <= rel * max(1.0, abs(b))


def test_irt_prob_basic():
    # symmetric case a=1,b=0,c=0,theta=0 => P should be 0.5
    p = irt_prob(1.0, 0.0, 0.0, 0.0)
    assert approx(p, 0.5)


def test_item_information_basic():
    # For c=0 the simplified info = (1.7*a)^2 * P^2
    a, b, c = 1.0, 0.0, 0.0
    theta = 0.0
    P = irt_prob(a, b, c, theta)
    info = item_information((a, b, c, 1.0), theta)
    expected = (1.7 * a) ** 2 * (P ** 2)
    assert approx(info, expected)


def test_item_information_c_one_returns_zero():
    # If c == 1, (1 - c) == 0 and function should return 0
    a, b, c = 1.0, 0.0, 1.0
    theta = 0.0
    info = item_information((a, b, c, 1.0), theta)
    assert info == 0.0


def test_item_information_extreme_theta_bounds():
    # Very large |theta-b| leads to P approx c or approx 1; info should be small
    a, b, c = 1.0, 0.0, 0.2
    theta_high = 1e6
    theta_low = -1e6
    info_high = item_information((a, b, c, 1.0), theta_high)
    info_low = item_information((a, b, c, 1.0), theta_low)
    assert info_high >= 0.0
    assert info_low >= 0.0
    # For extreme theta values info should be very small (close to 0)
    assert info_high < 1e-6 or math.isclose(info_high, 0.0, abs_tol=1e-6)
    assert info_low < 1e-6 or math.isclose(info_low, 0.0, abs_tol=1e-6)
