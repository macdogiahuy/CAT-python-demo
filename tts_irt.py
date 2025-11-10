"""Pure-Python IRT helpers used for unit tests.

This duplicates the logic of `irt_prob` and `item_information` from
`cat_service_api.py` but uses only the Python stdlib (math) so tests can run
without importing the whole service stack.
"""
import math
from typing import Sequence, Tuple


def irt_prob(a: float, b: float, c: float, theta: float) -> float:
    """3PL probability P(theta).

    P(θ) = c + (1 - c) / (1 + exp(-1.7 * a * (θ - b)))
    """
    try:
        expo = math.exp(-1.7 * a * (theta - b))
    except OverflowError:
        # math.exp overflow -> treat expo as +inf
        expo = float('inf')
    denom = 1.0 + expo
    return c + (1.0 - c) / denom


def item_information(item: Sequence[float], theta: float) -> float:
    """Fisher information for a 3PL item.

    item: sequence-like of (a, b, c, d) where d is unused (kept for parity
    with repo's item shape).
    """
    a, b, c, *_ = item
    P = irt_prob(a, b, c, theta)
    Q = 1.0 - P
    if P <= 0.0 or Q <= 0.0 or (1.0 - c) == 0.0:
        return 0.0
    # original repo computes: (1.7*a)**2 * ((P - c)**2 / ((1 - c)**2 * P * Q)) * P * Q
    # which simplifies (P*Q cancels) to:
    info = (1.7 * a) ** 2 * ((P - c) ** 2 / ((1.0 - c) ** 2))
    return info
