"""Outcome-free rule consensus for leveraged intraday ETF selection."""

from __future__ import annotations

from dataclasses import dataclass

import evaluate_full_universe_intraday_v12009_v12108_topk_cross_section as base
import numpy as np

FIRST_VERSION = 13309
LAST_VERSION = 13408
PRIOR_COMPARISON_CELLS = 327_183
ASSETS = np.asarray((3, 4), dtype=int)
SCHEDULES = base.residual.SCHEDULES
RULES = {
    "trend_flow_consensus": {
        "current_return": 1.0,
        "recent_return": 1.0,
        "relative_return": 1.0,
        "path_efficiency": 0.5,
        "signed_volume_imbalance": 0.75,
    },
    "vwap_reclaim": {
        "vwap_distance": 1.0,
        "rebound_from_low": 1.0,
        "return_acceleration": 0.75,
        "close_location": 0.5,
    },
    "failed_breakdown_repair": {
        "current_return": -0.5,
        "drawdown_from_high": -0.75,
        "rebound_from_low": 1.0,
        "intraday_range_position": 0.75,
        "return_acceleration": 1.0,
    },
    "flow_confirmed_breakout": {
        "current_return": 1.0,
        "recent_volume_ratio": 0.5,
        "signed_volume_imbalance": 1.0,
        "volume_acceleration": 0.75,
        "session_range": 0.25,
    },
    "compression_release": {
        "recent_volatility_ratio": -1.0,
        "recent_volume_ratio": 0.5,
        "return_acceleration": 1.0,
        "path_efficiency": 0.75,
        "intraday_range_position": 0.5,
    },
    "persistent_leadership": {
        "relative_return": 1.0,
        "current_rank": 0.75,
        "prior20_rank": 0.5,
        "prior20_return": 0.75,
        "path_efficiency": 0.5,
    },
    "gap_continuation": {
        "gap": 1.0,
        "current_return": 1.0,
        "relative_return": 0.75,
        "path_efficiency": 0.5,
        "signed_volume_imbalance": 0.5,
    },
    "gap_reversal": {
        "gap": -1.0,
        "current_return": -0.5,
        "rebound_from_low": 1.0,
        "return_acceleration": 0.75,
        "close_location": 0.5,
    },
    "balanced_path_quality": {
        "relative_return": 1.0,
        "path_efficiency": 1.0,
        "vwap_distance": 0.5,
        "close_location": 0.5,
        "signed_volume_imbalance": 0.75,
        "spy_volatility": -0.5,
    },
    "low_volatility_leadership": {
        "relative_return": 1.0,
        "current_rank": 0.75,
        "realized_volatility": -0.75,
        "recent_volatility_ratio": -0.5,
        "path_efficiency": 0.75,
    },
}


@dataclass(slots=True)
class RuleModel:
    family: str
    factors: tuple[str, ...]
    decision: int
    exit_bar: int
    mean: np.ndarray
    scale: np.ndarray
    coefficients: np.ndarray


def _fit(cube, family, schedule):
    rule = RULES[family]
    factors = tuple(rule)
    decision, exit_bar = schedule
    matrix = base._matrix(cube, factors, decision)
    train = cube.masks()["train_2022_2023"][:, None]
    finite = np.isfinite(matrix).all(axis=2)
    values = matrix[train & finite]
    mean, scale = values.mean(axis=0), values.std(axis=0)
    scale[scale < 1e-8] = 1.0
    coefficients = np.asarray(tuple(rule.values()), dtype=float)
    coefficients /= np.linalg.norm(coefficients)
    return RuleModel(
        family,
        factors,
        int(decision),
        int(exit_bar),
        mean,
        scale,
        coefficients,
    )


def _scores(cube, model):
    matrix = base._matrix(cube, model.factors, model.decision)
    score = np.einsum(
        "saf,f->sa", (matrix - model.mean) / model.scale, model.coefficients
    )
    return np.where(np.isfinite(matrix).all(axis=2), score, -np.inf)


def _definition_extra(model):
    return {
        "rule_weights": {
            factor: float(weight)
            for factor, weight in zip(model.factors, model.coefficients, strict=True)
        },
        "outcome_fit": False,
        "feature_scaling": "train_2022_2023_only",
    }


def _configure() -> None:
    base.FIRST_VERSION = FIRST_VERSION
    base.LAST_VERSION = LAST_VERSION
    base.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    base.ASSETS = ASSETS
    base.FACTOR_SETS = RULES
    base.SCHEDULES = SCHEDULES
    base.TOP_K = (1,)
    base.QUANTILES = (0.0, 0.20, 0.40, 0.60, 0.80)
    base.TARGETS = (0.25, 0.40)
    base.MECHANISM = "outcome_free_rule_consensus_alpha"
    base.DEFINITION_EXTRA = _definition_extra
    base._fit = _fit
    base._scores = _scores


if __name__ == "__main__":
    _configure()
    base.main()
