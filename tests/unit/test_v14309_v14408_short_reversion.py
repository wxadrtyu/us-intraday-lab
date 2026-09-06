from pathlib import Path
from runpy import run_path

import pandas as pd

SCRIPT = Path(__file__).parents[2] / "scripts" / "evaluate_us_market_v14309_v14408_short_reversion.py"
MODULE = run_path(str(SCRIPT), run_name="v14309_research")


def test_preregistered_grid_is_exact_and_unique() -> None:
    grid = MODULE["variants"]()
    assert [item.version for item in grid] == list(range(14309, 14409))
    assert len({(item.family, item.decision_bar, item.holding_bars) for item in grid}) == 100


def test_metrics_compound_and_measure_drawdown() -> None:
    result = MODULE["metrics"](pd.Series([0.10, -0.10, 0.05]))
    assert result["sessions"] == 3
    assert abs(result["total_return"] - 0.0395) < 1e-12
    assert abs(result["max_drawdown"] - 0.10) < 1e-12
