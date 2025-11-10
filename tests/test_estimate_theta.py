import math

from cat_service_api import estimate_theta


def test_estimate_theta_empty_administered_correct():
    items = [[1.0, 0.0, 0.2, 1.0]]
    administered = []
    responses = [1]
    theta_before = 0.0
    theta_after, theta_b = estimate_theta(items, administered, responses, theta_before)
    assert theta_b == theta_before
    assert math.isclose(theta_after, 0.3, rel_tol=1e-6, abs_tol=1e-9)


def test_estimate_theta_empty_administered_incorrect():
    items = [[1.0, 0.0, 0.2, 1.0]]
    administered = []
    responses = [0]
    theta_before = 0.0
    theta_after, theta_b = estimate_theta(items, administered, responses, theta_before)
    assert theta_b == theta_before
    assert math.isclose(theta_after, -0.3, rel_tol=1e-6, abs_tol=1e-9)


def test_estimate_theta_single_administered_triggers_fallback():
    items = [[1.0, 0.0, 0.2, 1.0]]
    administered = [0]
    responses = [1]
    theta_before = 1.2
    theta_after, theta_b = estimate_theta(items, administered, responses, theta_before)
    assert theta_b == theta_before
    assert math.isclose(theta_after, min(4.0, theta_before + 0.3), rel_tol=1e-6)
