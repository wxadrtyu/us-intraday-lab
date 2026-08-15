"""Stable-sign multi-factor rank ensembles with explicit factor selection diagnostics."""

from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import evaluate_full_universe_intraday_v34_multifactor as v34
import numpy as np
import search_full_universe_intraday_v12_robustness as v12
import search_full_universe_intraday_v13_regime_rotation as v13
import search_full_universe_intraday_v15_prior5 as v15

from us_intraday_lab.fast_intraday_research import metrics

FACTOR_TO_GROUP = {
    factor: group for group, factors in v34.FACTOR_GROUPS.items() for factor in factors
}
ALL_FACTORS = tuple(dict.fromkeys(f for values in v34.FACTOR_GROUPS.values() for f in values))
SELECTIONS = {
    **{
        f"set_{name}": {"pool": factors, "mode": "top6"}
        for name, factors in v34.FACTOR_SETS.items()
    },
    "stable_all": {"pool": ALL_FACTORS, "mode": "top6"},
    "group_balanced": {"pool": ALL_FACTORS, "mode": "group_balanced"},
}
WEIGHTINGS = ("equal", "reliability")
QUANTILES = (0.70, 0.85)
IC_FLOOR = 0.01


@dataclass(slots=True)
class RankModel:
    specification: dict[str, Any]
    factors: tuple[str, ...]
    mean: np.ndarray
    scale: np.ndarray
    direction: np.ndarray
    weights: np.ndarray
    threshold: float
    diagnostics: dict[str, dict[str, float]]


def _rank_vector(values: np.ndarray) -> np.ndarray:
    output = np.full(len(values), np.nan)
    finite = np.flatnonzero(np.isfinite(values))
    if len(finite) < 3:
        return output
    order = finite[np.argsort(values[finite], kind="stable")]
    output[order] = np.arange(len(order)) / (len(order) - 1)
    return output


def _spearman(left: np.ndarray, right: np.ndarray) -> float:
    valid = np.isfinite(left) & np.isfinite(right)
    if valid.sum() < 20:
        return math.nan
    ranked_left = _rank_vector(left[valid])
    ranked_right = _rank_vector(right[valid])
    deviation = float(np.std(ranked_left) * np.std(ranked_right))
    if deviation <= 1e-12:
        return math.nan
    return float(np.corrcoef(ranked_left, ranked_right)[0, 1])


def _select_factors(
    matrix: np.ndarray,
    label: np.ndarray,
    finite: np.ndarray,
    names: tuple[str, ...],
    train: np.ndarray,
    validation: np.ndarray,
    mode: str,
) -> tuple[tuple[str, ...], dict[str, dict[str, float]]]:
    diagnostics = {}
    stable = []
    for index, name in enumerate(names):
        train_mask = train[:, None] & finite
        validation_mask = validation[:, None] & finite
        train_ic = _spearman(matrix[:, :, index][train_mask], label[train_mask])
        validation_ic = _spearman(matrix[:, :, index][validation_mask], label[validation_mask])
        reliability = (
            min(abs(train_ic), abs(validation_ic)) if np.isfinite(train_ic + validation_ic) else 0.0
        )
        diagnostics[name] = {
            "train_ic": train_ic,
            "validation_ic": validation_ic,
            "reliability": reliability,
        }
        if (
            np.isfinite(train_ic)
            and np.isfinite(validation_ic)
            and train_ic * validation_ic > 0
            and reliability >= IC_FLOOR
        ):
            stable.append(name)
    if mode == "group_balanced":
        selected = []
        for group in v34.FACTOR_GROUPS:
            options = [name for name in stable if FACTOR_TO_GROUP[name] == group]
            if options:
                selected.append(max(options, key=lambda name: diagnostics[name]["reliability"]))
    else:
        selected = sorted(stable, key=lambda name: diagnostics[name]["reliability"], reverse=True)[
            :6
        ]
    return tuple(selected), diagnostics


def _fit_models(
    cube: v34.Cube,
    pool: tuple[str, ...],
    mode: str,
    profile: tuple[tuple[int, ...], ...],
    weighting: str,
    quantile: float,
) -> list[RankModel] | None:
    masks = cube.masks()
    train = masks["train_2022_2023"]
    validation = masks["2024"]
    models = []
    for slot, assets in zip(v34.SCHEDULE, profile, strict=True):
        specification = {**slot, "assets": assets}
        matrix, label, finite = v34._matrix(cube, specification, pool)
        selected, diagnostics = _select_factors(
            matrix, label, finite, pool, train, validation, mode
        )
        if len(selected) < 3:
            return None
        selected_indices = np.array([pool.index(name) for name in selected])
        selected_matrix = matrix[:, :, selected_indices]
        train_selected = (train[:, None] & finite)[:, :, None]
        values = np.where(train_selected, selected_matrix, np.nan)
        mean = np.nanmean(values, axis=(0, 1))
        scale = np.nanstd(values, axis=(0, 1))
        scale[scale < 1e-8] = 1.0
        direction = np.array(
            [np.sign(diagnostics[name]["train_ic"]) for name in selected], dtype=float
        )
        if weighting == "reliability":
            weights = np.array([diagnostics[name]["reliability"] for name in selected], dtype=float)
            weights /= weights.sum()
        else:
            weights = np.full(len(selected), 1.0 / len(selected))
        score = np.einsum("saf,f,f->sa", (selected_matrix - mean) / scale, direction, weights)
        score = np.where(finite, score, -np.inf)
        best = np.max(score, axis=1)
        threshold = float(np.quantile(best[validation & np.isfinite(best)], quantile))
        models.append(
            RankModel(
                specification,
                selected,
                mean,
                scale,
                direction,
                weights,
                threshold,
                diagnostics,
            )
        )
    return models


def _sleeve(cube: v34.Cube, model: RankModel, cost: float, delay: int) -> v12.ReturnStream:
    matrix, _, finite = v34._matrix(cube, model.specification, model.factors)
    score = np.einsum(
        "saf,f,f->sa", (matrix - model.mean) / model.scale, model.direction, model.weights
    )
    score = np.where(finite, score, -np.inf)
    local = np.argmax(score, axis=1)
    assets = np.asarray(model.specification["assets"], dtype=int)
    selected = assets[local]
    value = score[cube.rows, local]
    entry = int(model.specification["decision"]) + 1 + delay
    exit_bar = int(model.specification["exit"])
    active = np.isfinite(value) & (value >= model.threshold)
    active &= cube.first[cube.rows, entry, selected] <= entry * 5 + cube.boundary_tolerance
    active &= cube.first[cube.rows, exit_bar, selected] <= exit_bar * 5 + cube.boundary_tolerance
    active &= np.isfinite(cube.opens[cube.rows, entry, selected])
    active &= np.isfinite(cube.opens[cube.rows, exit_bar, selected])
    active &= np.isfinite(cube.opens[:, entry, 0])
    active &= np.isfinite(cube.opens[:, exit_bar, 0])
    active &= cube.opens[cube.rows, entry, selected] > 0
    active &= cube.opens[:, entry, 0] > 0
    returns = np.zeros(len(cube.sessions))
    returns[active] = (
        cube.opens[active, exit_bar, selected[active]] / cube.opens[active, entry, selected[active]]
        - 1.0
        - cost
    )
    benchmark = np.zeros(len(cube.sessions))
    benchmark[active] = cube.opens[active, exit_bar, 0] / cube.opens[active, entry, 0] - 1.0
    return v12.ReturnStream(returns, benchmark, active, active.astype(int))


def _stream(cube: v34.Cube, models: list[RankModel], cost: float, delay: int):
    return v13._combine([_sleeve(cube, model, cost, delay) for model in models])


def _normal_tail(value: float) -> float:
    return 0.5 * math.erfc(value / math.sqrt(2.0))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    development = v34.Cube(args.root, "alpaca", 0)
    planned_trials = len(SELECTIONS) * len(v34.PROFILES) * len(WEIGHTINGS) * len(QUANTILES)
    records = []
    model_sets: dict[str, list[RankModel]] = {}
    standard_streams: dict[str, v12.ReturnStream] = {}
    rejected_insufficient_factors = 0
    for selection_name, selection in SELECTIONS.items():
        pool = tuple(selection["pool"])
        mode = str(selection["mode"])
        for profile_name, profile in v34.PROFILES.items():
            for weighting in WEIGHTINGS:
                for quantile in QUANTILES:
                    models = _fit_models(development, pool, mode, profile, weighting, quantile)
                    if models is None:
                        rejected_insufficient_factors += 1
                        continue
                    definition = {
                        "factor_version": v34.FACTOR_VERSION,
                        "selection": selection_name,
                        "profile": profile_name,
                        "weighting": weighting,
                        "quantile": quantile,
                        "ic_floor": IC_FLOOR,
                    }
                    candidate_id = v12._identity(definition, "lev-v35r-")
                    model_sets[candidate_id] = models
                    scenario_streams = {
                        "standard": _stream(development, models, v34.STANDARD_COST, 0),
                        "cost_18bp": _stream(development, models, v34.STRESS_COST, 0),
                        "delay_5min_9bp": _stream(development, models, v34.STANDARD_COST, 1),
                    }
                    standard_streams[candidate_id] = scenario_streams["standard"]
                    observations = {
                        name: v13._observe(development, stream)
                        for name, stream in scenario_streams.items()
                    }
                    records.append(
                        {
                            "candidate_id": candidate_id,
                            "definition": definition,
                            "selected_factors_by_sleeve": {
                                model.specification["name"]: model.factors for model in models
                            },
                            "factor_diagnostics_by_sleeve": {
                                model.specification["name"]: model.diagnostics for model in models
                            },
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

    historical = v34.Cube(args.root, "historical", 0)
    folds = np.array_split(np.flatnonzero(development.masks()["development_all"]), 5)
    diagnostic_hits = 0
    eligible = 0
    for item in records:
        models = model_sets[item["candidate_id"]]
        historical_obs = v13._observe(historical, _stream(historical, models, v34.STANDARD_COST, 0))
        standard_stream = standard_streams[item["candidate_id"]]
        fold_obs = [
            metrics(
                standard_stream.values[index],
                standard_stream.benchmark[index],
                standard_stream.active[index],
            )
            for index in folds
        ]
        oos = item["standard"]["development_oos_2024_2025"]
        consumed = item["standard"]["consumed_2026_all"]
        hist = historical_obs["historical_2018_2020"]
        z_score = float(oos["information_ratio"]) * math.sqrt(max(1, int(oos["trades"])) / 252)
        bonferroni = min(1.0, 2.0 * _normal_tail(abs(z_score)) * planned_trials)
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
        item["development_folds"] = fold_obs
        item["multiple_comparison"] = {
            "planned_trials": planned_trials,
            "bonferroni_p": bonferroni,
        }
        item["gates"] = gates
        item["eligible_for_future_simulation_observation"] = all(gates.values())
        diagnostic_hits += int(gates["consumed_2026_total_above_20pct"])
        eligible += int(item["eligible_for_future_simulation_observation"])
    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "selection_contract": "factor signs require agreement in 2022-2023 and 2024; rank through 2025; 2026 post-freeze",
        "factor_selection": {
            "ic_floor": IC_FLOOR,
            "selections": SELECTIONS,
            "weightings": WEIGHTINGS,
            "minimum_factors_per_sleeve": 3,
        },
        "execution_contract": "long-only; gross<=1; no overnight; four non-overlapping sleeves",
        "scan": {
            "planned_trials": planned_trials,
            "evaluated_trials": len(records),
            "rejected_insufficient_factors": rejected_insufficient_factors,
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
    if records:
        best = max(
            records,
            key=lambda item: float(item["standard"]["consumed_2026_all"]["total_return"]),
        )
        print(
            json.dumps(
                {
                    "candidate_id": best["candidate_id"],
                    "definition": best["definition"],
                    "selected_factors_by_sleeve": best["selected_factors_by_sleeve"],
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
