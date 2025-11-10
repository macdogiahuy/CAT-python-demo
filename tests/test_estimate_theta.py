import ast
import textwrap
from types import SimpleNamespace

import numpy as np


def _load_estimate_theta_func():
    """Load estimate_theta from cat_service_api.py by extracting the function
    source and executing it in a minimal namespace to avoid side effects
    (like DB engine creation) that occur when importing the whole module.
    """
    path = "c:\\Users\\giahuy\\Downloads\\TTS_python\\cat_service_api.py"
    src = open(path, "r", encoding="utf-8").read()
    mod = ast.parse(src)
    func_node = None
    for node in mod.body:
        if isinstance(node, ast.FunctionDef) and node.name == "estimate_theta":
            func_node = node
            break
    if func_node is None:
        raise RuntimeError("estimate_theta not found in cat_service_api.py")

    func_src = ast.get_source_segment(src, func_node)

    ns = {
        "np": np,
        "SimpleNamespace": SimpleNamespace,
    }

    # Provide a lightweight dummy estimator so that the function definition
    # can be executed even if it references NumericalSearchEstimator. The
    # dummy will raise if actually used (we only test the fallback path).
    class DummyEstimator:
        def estimate(self, *args, **kwargs):
            raise RuntimeError("DummyEstimator should not be called in fallback tests")

    ns["NumericalSearchEstimator"] = DummyEstimator

    exec(textwrap.dedent(func_src), ns)
    return ns["estimate_theta"]


def test_estimate_theta_fallback_behaviour():
    estimate_theta = _load_estimate_theta_func()

    items = [[1.0, 0.0, 0.2, 1.0]]
    theta_before = 0.0

    # Case: no administered items, last response correct -> +0.3
    theta_after, theta_b = estimate_theta(items, [], [1], theta_before)
    assert theta_b == theta_before
    assert abs(theta_after - 0.3) < 1e-6

    # Case: no administered items, last response incorrect -> -0.3
    theta_after2, _ = estimate_theta(items, [], [0], theta_before)
    assert abs(theta_after2 - (-0.3)) < 1e-6

    # Case: single administered item triggers same fallback (+0.3)
    theta_before2 = 1.2
    theta_after3, tb3 = estimate_theta(items, [0], [1], theta_before2)
    assert tb3 == theta_before2
    assert abs(theta_after3 - min(4.0, theta_before2 + 0.3)) < 1e-6
