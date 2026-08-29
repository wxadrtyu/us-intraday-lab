from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3] / "scripts"))

import evaluate_full_universe_intraday_v2866_v2965_one_reentry as subject
import numpy as np
from test_v2266_post_entry_risk import cube


def test_one_reentry_is_next_open_and_charges_two_costs() -> None:
    data = cube()
    data.closes[0, 24, 3] = 96.0
    data.closes[0, 24, 0] = 99.0
    data.opens[0, 25, 3] = 97.0
    data.closes[0, 25, 3] = 98.0
    data.opens[0, 26, 3] = 99.0
    data.opens[0, 72, 3] = 105.0
    stream, valid, exits = subject.stopped_raw(
        data,
        np.array([3]),
        np.array([24]),
        np.array([True]),
        72,
        0.0009,
        0.03,
        0.05,
        1,
    )
    assert valid.tolist() == [True]
    assert exits.tolist() == [25]
    assert stream.component_trades.tolist() == [2]
    assert stream.values[0] == (97.0 / 100.0) * (105.0 / 99.0) - 1.0 - 0.0018
