from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parents[3] / "scripts"))

import evaluate_full_universe_intraday_v2266_v2365_post_entry_risk as subject
import numpy as np


def cube() -> SimpleNamespace:
    opens = np.full((1, 78, 5), 100.0)
    closes = opens.copy()
    first = np.broadcast_to(np.arange(78)[None, :, None] * 5, opens.shape).copy()
    last = first + 4
    return SimpleNamespace(
        sessions=np.array(["2024-01-02"]),
        rows=np.arange(1),
        opens=opens,
        closes=closes,
        first=first,
        last=last,
        boundary_tolerance=0,
    )


def test_stop_uses_completed_close_and_next_open() -> None:
    data = cube()
    data.closes[0, 24, 3] = 98.0
    data.opens[0, 25, 3] = 97.0
    data.opens[0, 72, 3] = 105.0
    stream, valid, exits = subject.stopped_raw(
        data,
        np.array([3]),
        np.array([24]),
        np.array([True]),
        72,
        0.0009,
        0.01,
        0.05,
        1,
    )
    assert valid.tolist() == [True]
    assert exits.tolist() == [25]
    assert stream.values[0] == 97.0 / 100.0 - 1.0 - 0.0009


def test_incomplete_close_cannot_trigger() -> None:
    data = cube()
    data.closes[0, 24, 3] = 95.0
    data.last[0, 24, 3] = 122
    data.opens[0, 72, 3] = 103.0
    stream, valid, exits = subject.stopped_raw(
        data,
        np.array([3]),
        np.array([24]),
        np.array([True]),
        72,
        0.0009,
        0.01,
        0.05,
        1,
    )
    assert valid.tolist() == [True]
    assert exits.tolist() == [72]
    assert stream.values[0] == 103.0 / 100.0 - 1.0 - 0.0009


def test_missing_triggered_next_open_invalidates_session() -> None:
    data = cube()
    data.closes[0, 24, 3] = 98.0
    data.opens[0, 25, 3] = np.nan
    stream, valid, exits = subject.stopped_raw(
        data,
        np.array([3]),
        np.array([24]),
        np.array([True]),
        72,
        0.0009,
        0.01,
        0.05,
        1,
    )
    assert valid.tolist() == [False]
    assert exits.tolist() == [72]
    assert stream.active.tolist() == [False]
    assert stream.values.tolist() == [0.0]
