"""Small NumPy primitives for checkpointable intraday strategy research."""

from __future__ import annotations

import math

import numpy as np


def metrics(
    returns: np.ndarray, benchmark_returns: np.ndarray, active: np.ndarray
) -> dict[str, float | int]:
    """Compute cost-aware daily metrics against an exposure-matched benchmark."""

    values = np.asarray(returns, dtype=float)
    benchmark = np.where(np.asarray(active, dtype=bool), benchmark_returns, 0.0)
    if values.ndim != 1 or benchmark.shape != values.shape or len(values) == 0:
        raise ValueError("metric inputs must be equally sized non-empty vectors")
    if not np.isfinite(values).all() or not np.isfinite(benchmark).all():
        raise ValueError("metric inputs must be finite")
    equity = np.cumprod(1.0 + values)
    annualized = float(equity[-1] ** (252.0 / len(values)) - 1.0)
    peak = np.maximum.accumulate(np.concatenate(([1.0], equity)))[:-1]
    drawdown = float(np.max(1.0 - equity / peak))
    gains = float(values[values > 0.0].sum())
    losses = abs(float(values[values < 0.0].sum()))
    active_returns = values - benchmark
    deviation = float(np.std(active_returns, ddof=1)) if len(values) > 1 else 0.0
    information_ratio = (
        float(np.mean(active_returns) / deviation * math.sqrt(252.0))
        if deviation > 0.0
        else -math.inf
    )
    return {
        "annualized_return": annualized,
        "total_return": float(equity[-1] - 1.0),
        "max_drawdown": drawdown,
        "profit_factor": gains / losses if losses else math.inf,
        "information_ratio": information_ratio,
        "trades": int(np.asarray(active, dtype=bool).sum()),
    }
