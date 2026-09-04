"""Causal intraday return-sign topology alpha."""

from __future__ import annotations

from dataclasses import dataclass

import evaluate_full_universe_intraday_v12009_v12108_topk_cross_section as base
import numpy as np

FIRST_VERSION = 14109
LAST_VERSION = 14208
PRIOR_COMPARISON_CELLS = 335_183
ASSETS = np.asarray((3, 4), dtype=int)
SCHEDULES = (
    (8, 35),
    (11, 41),
    (14, 47),
    (17, 53),
    (20, 59),
    (23, 65),
    (29, 71),
    (35, 72),
    (41, 77),
    (47, 77),
)
REPRESENTATIONS = {
    "raw_short": ("raw", 1, 5),
    "raw_long": ("raw", 1, 9),
    "raw_two_bar": ("raw", 2, 6),
    "raw_three_bar": ("raw", 3, 6),
    "market_relative_short": ("market_relative", 1, 5),
    "market_relative_long": ("market_relative", 1, 9),
    "anchor_relative_short": ("anchor_relative", 1, 5),
    "anchor_relative_long": ("anchor_relative", 1, 9),
    "anchor_agreement": ("anchor_agreement", 1, 7),
    "cross_leveraged": ("cross_leveraged", 1, 7),
}
ANCHORS = (1, 10)
FACTORS = (
    "mean_sign",
    "transition_rate",
    "reversal_asymmetry",
    "signed_terminal_run",
    "sign_entropy",
    "signed_jump_concentration",
    "late_early_sign_balance",
)
_MATRIX_CACHE: dict[tuple, np.ndarray] = {}


@dataclass(slots=True)
class SignTopologyModel:
    family: str
    factors: tuple[str, ...]
    decision: int
    exit_bar: int
    mean: np.ndarray
    scale: np.ndarray
    coefficients: np.ndarray
    source: str
    aggregation_bars: int
    window_bars: int


def _source_returns(cube, source: str, position: int) -> np.ndarray:
    asset = int(ASSETS[position])
    values = cube.bar_return[:, :, asset]
    if source == "raw":
        return values
    if source == "market_relative":
        return values - cube.bar_return[:, :, 0]
    if source == "anchor_relative":
        return values - cube.bar_return[:, :, ANCHORS[position]]
    if source == "anchor_agreement":
        anchor = cube.bar_return[:, :, ANCHORS[position]]
        return np.sign(values) * (np.sign(values) == np.sign(anchor))
    if source == "cross_leveraged":
        other = int(ASSETS[1 - position])
        return values - cube.bar_return[:, :, other]
    raise ValueError(f"UNKNOWN_SIGN_TOPOLOGY_SOURCE:{source}")


def _aggregate_window(
    values: np.ndarray, decision: int, window: int, aggregation: int
) -> np.ndarray:
    end = decision + 1
    start = end - window - aggregation + 1
    if start < 1:
        return np.full((values.shape[0], window), np.nan)
    return sum(values[:, start + offset : start + offset + window] for offset in range(aggregation))


def _topology_features(sequence: np.ndarray) -> np.ndarray:
    sign = np.sign(sequence)
    valid = np.isfinite(sequence).all(axis=1) & (np.abs(sequence).sum(axis=1) > 0)
    mean_sign = np.mean(sign, axis=1)
    down_up = np.mean((sign[:, :-1] < 0) & (sign[:, 1:] > 0), axis=1)
    up_down = np.mean((sign[:, :-1] > 0) & (sign[:, 1:] < 0), axis=1)
    transition = np.mean(sign[:, 1:] != sign[:, :-1], axis=1)
    terminal = sign[:, -1]
    terminal_equal = sign[:, ::-1] == terminal[:, None]
    terminal_run = np.cumprod(terminal_equal, axis=1).sum(axis=1)
    signed_run = terminal * terminal_run / sign.shape[1]
    positive_share = np.clip(np.mean(sign > 0, axis=1), 1e-12, 1 - 1e-12)
    entropy = -(
        positive_share * np.log(positive_share)
        + (1 - positive_share) * np.log(1 - positive_share)
    ) / np.log(2)
    jump_index = np.argmax(np.abs(sequence), axis=1)
    jump = np.take_along_axis(sequence, jump_index[:, None], axis=1)[:, 0]
    jump_concentration = jump / np.maximum(np.abs(sequence).sum(axis=1), 1e-12)
    split = sign.shape[1] // 2
    phase_balance = np.mean(sign[:, split:], axis=1) - np.mean(sign[:, :split], axis=1)
    result = np.stack(
        (
            mean_sign,
            transition,
            down_up - up_down,
            signed_run,
            entropy,
            jump_concentration,
            phase_balance,
        ),
        axis=1,
    )
    result[~valid] = np.nan
    return result


def _sign_topology_matrix(cube, model: SignTopologyModel) -> np.ndarray:
    key = (
        id(cube),
        model.family,
        model.decision,
        model.exit_bar,
        model.source,
        model.aggregation_bars,
        model.window_bars,
    )
    if key in _MATRIX_CACHE:
        return _MATRIX_CACHE[key]
    pieces = []
    for position in range(len(ASSETS)):
        source = _source_returns(cube, model.source, position)
        sequence = _aggregate_window(
            source, model.decision, model.window_bars, model.aggregation_bars
        )
        pieces.append(_topology_features(sequence))
    matrix = np.stack(pieces, axis=1)
    _MATRIX_CACHE[key] = matrix
    return matrix


def _fit(cube, family, schedule):
    source, aggregation, window = REPRESENTATIONS[family]
    decision, exit_bar = schedule
    shell = SignTopologyModel(
        family,
        FACTORS,
        decision,
        exit_bar,
        np.empty(0),
        np.empty(0),
        np.empty(0),
        source,
        aggregation,
        window,
    )
    matrix = _sign_topology_matrix(cube, shell)
    entry = decision + 1
    asset_return = cube.opens[:, exit_bar, ASSETS] / cube.opens[:, entry, ASSETS] - 1.0
    spy_return = cube.opens[:, exit_bar, 0] / cube.opens[:, entry, 0] - 1.0
    target = asset_return - spy_return[:, None]
    quality = (
        (cube.first[:, entry, ASSETS] <= entry * 5)
        & (cube.first[:, exit_bar, ASSETS] <= exit_bar * 5)
        & np.isfinite(matrix).all(axis=2)
        & np.isfinite(target)
    )
    train = cube.masks()["train_2022_2023"][:, None] & quality
    values, labels = matrix[train], target[train]
    mean, scale = values.mean(axis=0), values.std(axis=0)
    scale[scale < 1e-8] = 1.0
    standardized = (values - mean) / scale
    coefficients = np.linalg.solve(
        standardized.T @ standardized + base.ALPHA * np.eye(matrix.shape[2]),
        standardized.T @ labels,
    )
    shell.mean, shell.scale, shell.coefficients = mean, scale, coefficients
    return shell


def _scores(cube, model):
    matrix = _sign_topology_matrix(cube, model)
    score = np.einsum(
        "saf,f->sa", (matrix - model.mean) / model.scale, model.coefficients
    )
    return np.where(np.isfinite(matrix).all(axis=2), score, -np.inf)


def _configure() -> None:
    base.FIRST_VERSION = FIRST_VERSION
    base.LAST_VERSION = LAST_VERSION
    base.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    base.ASSETS = ASSETS
    base.FACTOR_SETS = REPRESENTATIONS
    base.SCHEDULES = SCHEDULES
    base.TOP_K = (1,)
    base.QUANTILES = (0.0, 0.20, 0.40, 0.60, 0.80)
    base.TARGETS = (0.25, 0.40)
    base.MECHANISM = "causal_intraday_return_sign_topology_alpha"
    base.DEFINITION_EXTRA = lambda model: {
        "source": model.source,
        "aggregation_bars": model.aggregation_bars,
        "window_bars": model.window_bars,
        "feature_transform": "causal_return_sign_topology",
        "training_target": "asset_return_minus_spy_return",
    }
    base._fit = _fit
    base._scores = _scores


if __name__ == "__main__":
    _configure()
    base.main()
