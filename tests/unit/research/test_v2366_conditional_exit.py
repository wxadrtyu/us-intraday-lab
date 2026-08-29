from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3] / "scripts"))

import evaluate_full_universe_intraday_v2366_v2465_conditional_exit as subject
import numpy as np
from test_v2266_post_entry_risk import cube


def run(data):
    return subject.stopped_raw(
        data,
        np.array([3]),
        np.array([24]),
        np.array([True]),
        72,
        0.0009,
        0.03,
        0.02,
        1,
    )


def test_hard_loss_requires_market_confirmation() -> None:
    data = cube()
    data.closes[0, 24, 3] = 96.0
    data.closes[0, 24, 0] = 100.0
    _, valid, exits = run(data)
    assert valid.tolist() == [True]
    assert exits.tolist() == [72]


def test_joint_hard_loss_exits_next_open() -> None:
    data = cube()
    data.closes[0, 24, 3] = 96.0
    data.closes[0, 24, 0] = 99.0
    data.opens[0, 25, 3] = 95.0
    stream, _, exits = run(data)
    assert exits.tolist() == [25]
    assert stream.values[0] == 95.0 / 100.0 - 1.0 - 0.0009


def test_activated_profit_giveback_does_not_require_market_loss() -> None:
    data = cube()
    data.closes[0, 24, 3] = 102.0
    data.closes[0, 25, 3] = 99.0
    data.opens[0, 26, 3] = 98.0
    _, _, exits = run(data)
    assert exits.tolist() == [26]
