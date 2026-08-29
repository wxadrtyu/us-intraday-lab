import importlib
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
robust = importlib.import_module("evaluate_full_universe_intraday_v2066_v2165_robust_concentration")


def test_robust_grid_and_versions_are_frozen():
    p = json.loads(robust.PROPOSAL.read_text())
    assert p["first_version"] == 2066 and p["last_version"] == 2165
    assert 5 * 5 * 4 == p["hypothesis_count"] == 100
    assert p["missingness_contract"]["minimum_observed_factors"] == 12


def test_design_imputes_sparse_values_and_retains_indicators():
    matrix = np.arange(32, dtype=float).reshape(2, 16)
    matrix[0, :4] = np.nan
    matrix[1, :5] = np.nan
    design, eligible = robust._design(matrix, np.arange(16, dtype=float))
    assert eligible.tolist() == [True, False]
    np.testing.assert_allclose(design[0, :4], np.arange(4))
    np.testing.assert_allclose(design[0, 16:20], 1)
    np.testing.assert_allclose(design[0, 20:], 0)
