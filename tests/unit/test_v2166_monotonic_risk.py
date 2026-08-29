import importlib
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
monotonic = importlib.import_module("evaluate_full_universe_intraday_v2166_v2265_monotonic_risk")


def test_monotonic_grid_is_one_hundred_new_versions():
    p = json.loads(monotonic.PROPOSAL.read_text())
    assert (p["first_version"], p["last_version"], p["hypothesis_count"]) == (2166, 2265, 100)
    assert len(p["factor_contract"]) == 7


def test_weak_breadth_and_high_volatility_lower_score():
    model = {
        "minimum_observed": 5,
        "imputation": [0] * 7,
        "mean": [0] * 7,
        "scale": [1] * 7,
        "directions": monotonic.DIRECTIONS.tolist(),
    }
    healthy = np.array([[1, -1, 1, -1, 1, 1, 1]], dtype=float)
    weak = np.array([[1, 1, -1, 1, 1, 1, 1]], dtype=float)
    assert monotonic._score(healthy, model)[0] > monotonic._score(weak, model)[0]
