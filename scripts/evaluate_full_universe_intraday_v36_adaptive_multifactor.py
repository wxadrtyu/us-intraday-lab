"""Causal rolling-IC adaptive multi-factor rank strategy campaign."""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path
from typing import Any

import evaluate_full_universe_intraday_v34_multifactor as v34
import numpy as np
import search_full_universe_intraday_v12_robustness as v12
import search_full_universe_intraday_v13_regime_rotation as v13
import search_full_universe_intraday_v15_prior5 as v15

from us_intraday_lab.fast_intraday_research import metrics

ALL_FACTORS = tuple(dict.fromkeys(f for values in v34.FACTOR_GROUPS.values() for f in values))
POOLS = {
    "all": ALL_FACTORS,
    "trend_quality": tuple(
        dict.fromkeys(
            v34.FACTOR_GROUPS["trend"]
            + v34.FACTOR_GROUPS["flow"]
            + v34.FACTOR_GROUPS["structure"]
            + v34.FACTOR_GROUPS["volatility"]
        )
    ),
    "cross_regime": tuple(
        dict.fromkeys(
            v34.FACTOR_GROUPS["trend"]
            + v34.FACTOR_GROUPS["cross_section"]
            + v34.FACTOR_GROUPS["state"]
        )
    ),
    "reversal_state": tuple(
        dict.fromkeys(
            ("current_return", "recent_return")
            + v34.FACTOR_GROUPS["flow"]
            + v34.FACTOR_GROUPS["structure"]
            + v34.FACTOR_GROUPS["state"]
        )
    ),
}
LOOKBACKS = (126, 252)
TOP_COUNTS = (3, 5)
SCORE_THRESHOLDS = (0.0, 0.5, 1.0)
IC_FLOOR = 0.01


def _prefix(values: np.ndarray) -> np.ndarray:
    return np.concatenate((np.zeros((1, values.shape[1])), np.cumsum(values, axis=0)), axis=0)


def _window(prefix: np.ndarray, start: np.ndarray, end: np.ndarray) -> np.ndarray:
    return prefix[end] - prefix[start]


def _rolling_statistics(
    matrix: np.ndarray, label: np.ndarray, finite: np.ndarray, lookback: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    sessions, _, factor_count = matrix.shape
    count = np.zeros((sessions, factor_count))
    sum_x = np.zeros_like(count)
    sum_y = np.zeros_like(count)
    sum_x2 = np.zeros_like(count)
    sum_y2 = np.zeros_like(count)
    sum_xy = np.zeros_like(count)
    for factor in range(factor_count):
        valid = finite & np.isfinite(matrix[:, :, factor]) & np.isfinite(label)
        x = np.where(valid, matrix[:, :, factor], 0.0)
        y = np.where(valid, label, 0.0)
        count[:, factor] = valid.sum(axis=1)
        sum_x[:, factor] = x.sum(axis=1)
        sum_y[:, factor] = y.sum(axis=1)
        sum_x2[:, factor] = (x * x).sum(axis=1)
        sum_y2[:, factor] = (y * y).sum(axis=1)
        sum_xy[:, factor] = (x * y).sum(axis=1)
    prefixes = tuple(_prefix(item) for item in (count, sum_x, sum_y, sum_x2, sum_y2, sum_xy))
    rows = np.arange(sessions)
    start = np.maximum(0, rows - lookback)
    middle = np.maximum(start, rows - lookback // 2)

    def statistics(left: np.ndarray, right: np.ndarray):
        n, sx, sy, sx2, sy2, sxy = (_window(prefix, left, right) for prefix in prefixes)
        covariance = sxy - np.divide(sx * sy, n, out=np.zeros_like(sxy), where=n > 0)
        variance_x = sx2 - np.divide(sx * sx, n, out=np.zeros_like(sx2), where=n > 0)
        variance_y = sy2 - np.divide(sy * sy, n, out=np.zeros_like(sy2), where=n > 0)
        denominator = np.sqrt(np.maximum(variance_x * variance_y, 0.0))
        correlation = np.divide(
            covariance,
            denominator,
            out=np.full_like(covariance, np.nan),
            where=(n >= 30) & (denominator > 1e-12),
        )
        mean = np.divide(sx, n, out=np.full_like(sx, np.nan), where=n > 0)
        variance = np.divide(variance_x, n, out=np.full_like(variance_x, np.nan), where=n > 0)
        return correlation, mean, np.sqrt(np.maximum(variance, 0.0))

    first_ic, _, _ = statistics(start, middle)
    second_ic, _, _ = statistics(middle, rows)
    _, mean, scale = statistics(start, rows)
    scale[scale < 1e-8] = np.nan
    return first_ic, second_ic, mean, scale


def _signal(
    cube: v34.Cube,
    specification: dict[str, Any],
    factors: tuple[str, ...],
    lookback: int,
    top_count: int,
    score_threshold: float,
) -> tuple[np.ndarray, np.ndarray, dict[str, int]]:
    matrix, label, finite = v34._matrix(cube, specification, factors)
    first_ic, second_ic, mean, scale = _rolling_statistics(matrix, label, finite, lookback)
    sessions = matrix.shape[0]
    selected = np.full(sessions, -1, dtype=int)
    active = np.zeros(sessions, dtype=bool)
    factor_usage = {name: 0 for name in factors}
    asset_indices = np.asarray(specification["assets"], dtype=int)
    for row in range(lookback, sessions):
        reliability = np.minimum(np.abs(first_ic[row]), np.abs(second_ic[row]))
        stable = (
            np.isfinite(reliability)
            & (first_ic[row] * second_ic[row] > 0)
            & (reliability >= IC_FLOOR)
            & np.isfinite(mean[row])
            & np.isfinite(scale[row])
        )
        choices = np.flatnonzero(stable)
        if len(choices) < top_count:
            continue
        choices = choices[np.argsort(reliability[choices])[-top_count:]]
        current_values = matrix[row][:, choices]
        valid_assets = np.isfinite(current_values).all(axis=1)
        if not valid_assets.any():
            continue
        direction = np.sign(second_ic[row, choices])
        weights = reliability[choices]
        weights /= weights.sum()
        standardized = (current_values - mean[row, choices]) / scale[row, choices]
        scores = standardized @ (direction * weights)
        scores = np.where(valid_assets, scores, -np.inf)
        local = int(np.argmax(scores))
        if np.isfinite(scores[local]) and scores[local] >= score_threshold:
            selected[row] = int(asset_indices[local])
            active[row] = True
            for choice in choices:
                factor_usage[factors[choice]] += 1
    return selected, active, factor_usage


def _sleeve(
    cube: v34.Cube,
    specification: dict[str, Any],
    selected: np.ndarray,
    active: np.ndarray,
    cost: float,
    delay: int,
) -> v12.ReturnStream:
    entry = int(specification["decision"]) + 1 + delay
    exit_bar = int(specification["exit"])
    safe = np.maximum(selected, 0)
    executable = active.copy()
    executable &= cube.first[cube.rows, entry, safe] <= entry * 5 + cube.boundary_tolerance
    executable &= cube.first[cube.rows, exit_bar, safe] <= exit_bar * 5 + cube.boundary_tolerance
    executable &= np.isfinite(cube.opens[cube.rows, entry, safe])
    executable &= np.isfinite(cube.opens[cube.rows, exit_bar, safe])
    executable &= np.isfinite(cube.opens[:, entry, 0])
    executable &= np.isfinite(cube.opens[:, exit_bar, 0])
    executable &= cube.opens[cube.rows, entry, safe] > 0
    executable &= cube.opens[:, entry, 0] > 0
    values = np.zeros(len(cube.sessions))
    values[executable] = (
        cube.opens[executable, exit_bar, safe[executable]]
        / cube.opens[executable, entry, safe[executable]]
        - 1.0
        - cost
    )
    benchmark = np.where(
        executable, cube.opens[:, exit_bar, 0] / cube.opens[:, entry, 0] - 1.0, 0.0
    )
    return v12.ReturnStream(values, benchmark, executable, executable.astype(int))


def _build_streams(
    cube: v34.Cube,
    factors: tuple[str, ...],
    profile: tuple[tuple[int, ...], ...],
    lookback: int,
    top_count: int,
    score_threshold: float,
):
    standard = []
    cost = []
    delay = []
    usage = {}
    for slot, assets in zip(v34.SCHEDULE, profile, strict=True):
        specification = {**slot, "assets": assets}
        selected, active, factor_usage = _signal(
            cube, specification, factors, lookback, top_count, score_threshold
        )
        usage[slot["name"]] = factor_usage
        standard.append(_sleeve(cube, specification, selected, active, v34.STANDARD_COST, 0))
        cost.append(_sleeve(cube, specification, selected, active, v34.STRESS_COST, 0))
        delay.append(_sleeve(cube, specification, selected, active, v34.STANDARD_COST, 1))
    return v13._combine(standard), v13._combine(cost), v13._combine(delay), usage


def _observe_development(cube: v34.Cube, stream: v12.ReturnStream):
    masks = cube.masks()
    names = v15.DEVELOPMENT_NAMES + ("development_oos_2024_2025",)
    return {
        name: metrics(
            stream.values[masks[name]],
            stream.benchmark[masks[name]],
            stream.active[masks[name]],
        )
        for name in names
    }


def _normal_tail(value: float) -> float:
    return 0.5 * math.erfc(value / math.sqrt(2.0))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    development = v34.Cube(args.root, "alpaca", 0)
    records = []
    streams: dict[str, tuple[v12.ReturnStream, v12.ReturnStream, v12.ReturnStream]] = {}
    for pool_name, factors in POOLS.items():
        for profile_name, profile in v34.PROFILES.items():
            for lookback in LOOKBACKS:
                for top_count in TOP_COUNTS:
                    for threshold in SCORE_THRESHOLDS:
                        definition = {
                            "factor_version": v34.FACTOR_VERSION,
                            "pool": pool_name,
                            "profile": profile_name,
                            "lookback": lookback,
                            "top_count": top_count,
                            "score_threshold": threshold,
                            "ic_floor": IC_FLOOR,
                        }
                        candidate_id = v12._identity(definition, "lev-v36a-")
                        standard, cost, delay, usage = _build_streams(
                            development,
                            factors,
                            profile,
                            lookback,
                            top_count,
                            threshold,
                        )
                        streams[candidate_id] = (standard, cost, delay)
                        observations = {
                            "standard": _observe_development(development, standard),
                            "cost_18bp": _observe_development(development, cost),
                            "delay_5min_9bp": _observe_development(development, delay),
                        }
                        records.append(
                            {
                                "candidate_id": candidate_id,
                                "definition": definition,
                                "factor_usage": usage,
                                "development_rank": [
                                    min(
                                        float(observations["standard"][name]["annualized_return"])
                                        for name in v15.DEVELOPMENT_NAMES
                                    ),
                                    float(
                                        observations["cost_18bp"]["development_oos_2024_2025"][
                                            "annualized_return"
                                        ]
                                    ),
                                    float(
                                        observations["cost_18bp"]["development_oos_2024_2025"][
                                            "information_ratio"
                                        ]
                                    ),
                                ],
                                **observations,
                            }
                        )
    records.sort(key=lambda item: tuple(item["development_rank"]), reverse=True)

    # Development ranking is frozen before diagnostic metrics or historical data are loaded.
    historical = v34.Cube(args.root, "historical", 0)
    folds = np.array_split(np.flatnonzero(development.masks()["development_all"]), 5)
    total_trials = len(records)
    diagnostic_hits = 0
    eligible = 0
    for item in records:
        definition = item["definition"]
        profile = v34.PROFILES[str(definition["profile"])]
        factors = POOLS[str(definition["pool"])]
        standard, cost, delay = streams[item["candidate_id"]]
        item["standard"] = v13._observe(development, standard)
        item["cost_18bp"] = v13._observe(development, cost)
        item["delay_5min_9bp"] = v13._observe(development, delay)
        historical_standard, _, _, historical_usage = _build_streams(
            historical,
            factors,
            profile,
            int(definition["lookback"]),
            int(definition["top_count"]),
            float(definition["score_threshold"]),
        )
        historical_obs = v13._observe(historical, historical_standard)
        fold_obs = [
            metrics(standard.values[index], standard.benchmark[index], standard.active[index])
            for index in folds
        ]
        oos = item["standard"]["development_oos_2024_2025"]
        consumed = item["standard"]["consumed_2026_all"]
        hist = historical_obs["historical_2018_2020"]
        z_score = float(oos["information_ratio"]) * math.sqrt(max(1, int(oos["trades"])) / 252)
        bonferroni = min(1.0, 2.0 * _normal_tail(abs(z_score)) * total_trials)
        gates = {
            "standard_primary": v15._primary(item["standard"]),
            "cost_18bp_primary": v15._primary(item["cost_18bp"]),
            "delay_5min_primary": v15._primary(item["delay_5min_9bp"]),
            "four_of_five_positive_folds": sum(
                float(fold["annualized_return"]) > 0 for fold in fold_obs
            )
            >= 4,
            "historical_positive_mdd_below_20pct": float(hist["annualized_return"]) > 0
            and float(hist["max_drawdown"]) < 0.20,
            "consumed_2026_total_above_20pct": float(consumed["total_return"]) > 0.20,
            "consumed_2026_mdd_below_20pct": float(consumed["max_drawdown"]) < 0.20,
            "consumed_2026_ir_at_least_1": float(consumed["information_ratio"]) >= 1.0,
            "multiple_comparison_bonferroni_5pct": bonferroni < 0.05,
            "ablation_evaluated": False,
            "start_date_stress_evaluated": False,
            "parameter_neighborhood_evaluated": False,
        }
        item["historical_cross_source"] = historical_obs
        item["historical_factor_usage"] = historical_usage
        item["development_folds"] = fold_obs
        item["multiple_comparison"] = {
            "total_trials": total_trials,
            "bonferroni_p": bonferroni,
        }
        item["gates"] = gates
        item["eligible_for_future_simulation_observation"] = all(gates.values())
        diagnostic_hits += int(gates["consumed_2026_total_above_20pct"])
        eligible += int(item["eligible_for_future_simulation_observation"])
    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "selection_contract": "rolling factor IC uses only prior sessions; hyperparameters rank on 2022-2025; 2026 metrics post-freeze",
        "factor_model": {
            "pools": POOLS,
            "lookbacks": LOOKBACKS,
            "top_counts": TOP_COUNTS,
            "score_thresholds": SCORE_THRESHOLDS,
            "ic_floor": IC_FLOOR,
            "production_catalog_mutated": False,
        },
        "execution_contract": "long-only; gross<=1; no overnight; four non-overlapping sleeves",
        "scan": {
            "pools": len(POOLS),
            "profiles": len(v34.PROFILES),
            "lookbacks": len(LOOKBACKS),
            "top_counts": len(TOP_COUNTS),
            "score_thresholds": len(SCORE_THRESHOLDS),
            "total_trials": total_trials,
            "frontier_size": len(records),
            "elapsed_seconds": time.perf_counter() - started,
        },
        "diagnostic_2026_above_20_count": diagnostic_hits,
        "eligible_count": eligible,
        "frontier": records,
    }
    v12._atomic(args.output, payload)
    print(
        json.dumps(
            {"scan": payload["scan"], "diagnostic_hits": diagnostic_hits, "eligible": eligible}
        )
    )
    best = max(
        records, key=lambda item: float(item["standard"]["consumed_2026_all"]["total_return"])
    )
    print(
        json.dumps(
            {
                "candidate_id": best["candidate_id"],
                "definition": best["definition"],
                "development_rank": best["development_rank"],
                "oos": best["standard"]["development_oos_2024_2025"],
                "cost_oos": best["cost_18bp"]["development_oos_2024_2025"],
                "delay_oos": best["delay_5min_9bp"]["development_oos_2024_2025"],
                "historical": best["historical_cross_source"]["historical_2018_2020"],
                "consumed_2026": best["standard"]["consumed_2026_all"],
                "gates": best["gates"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
