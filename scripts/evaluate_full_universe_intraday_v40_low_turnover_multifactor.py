"""One-trade-per-day stable multi-factor search with post-freeze diagnostics."""

from __future__ import annotations

import argparse
import itertools
import json
import math
import time
from pathlib import Path

import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v35_rank_ensemble as v35
import evaluate_full_universe_intraday_v38_multifactor_sleeve_beam as v38
import numpy as np
import search_full_universe_intraday_v12_robustness as v12
import search_full_universe_intraday_v13_regime_rotation as v13
import search_full_universe_intraday_v15_prior5 as v15

from us_intraday_lab.fast_intraday_research import metrics

DECISIONS = (2, 5, 8, 11, 17, 23, 29, 35, 41, 47, 53)
EXITS = (47, 56, 66, 72, 77)
UNIVERSES = {
    "leveraged": (3, 4),
    "risk": (1, 2, 3, 4),
    "sectors": tuple(range(5, 16)),
    "all": tuple(range(1, 16)),
}
IC_FLOORS = (0.005, 0.01, 0.02)
SELECTION_MODES = ("group_balanced", "top6")
WEIGHTINGS = ("equal", "reliability")
SCORE_THRESHOLDS = (0.0, 0.5, 1.0, 1.5)


def _observe(cube: v34.Cube, stream: v12.ReturnStream, full: bool = False):
    masks = cube.masks()
    names = (
        tuple(name for name, mask in masks.items() if mask.any())
        if full
        else v15.DEVELOPMENT_NAMES + ("development_oos_2024_2025",)
    )
    return {
        name: metrics(
            stream.values[masks[name]], stream.benchmark[masks[name]], stream.active[masks[name]]
        )
        for name in names
    }


def _rank(standard: dict, cost: dict, delay: dict):
    return (
        min(float(standard[name]["annualized_return"]) for name in v15.DEVELOPMENT_NAMES),
        min(
            float(cost["development_oos_2024_2025"]["annualized_return"]),
            float(delay["development_oos_2024_2025"]["annualized_return"]),
        ),
        min(
            float(cost["development_oos_2024_2025"]["information_ratio"]),
            float(delay["development_oos_2024_2025"]["information_ratio"]),
        ),
    )


def _normal_tail(value: float) -> float:
    return 0.5 * math.erfc(value / math.sqrt(2.0))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--frontier", default=500, type=int)
    args = parser.parse_args()
    started = time.perf_counter()
    development = v34.Cube(args.root, "alpaca", 0)
    candidates = []
    planned = 0
    fitted = 0
    for decision, exit_bar, (universe_name, assets) in itertools.product(
        DECISIONS, EXITS, UNIVERSES.items()
    ):
        if exit_bar <= decision + 2:
            continue
        specification = {
            "name": "daily_once",
            "decision": decision,
            "exit": exit_bar,
            "assets": assets,
        }
        matrix, finite, diagnostics = v38._diagnostics(development, specification)
        for ic_floor, selection_mode, weighting, threshold in itertools.product(
            IC_FLOORS, SELECTION_MODES, WEIGHTINGS, SCORE_THRESHOLDS
        ):
            planned += 1
            model = v38._model(
                development,
                specification,
                matrix,
                finite,
                diagnostics,
                ic_floor,
                selection_mode,
                weighting,
                threshold,
            )
            if model is None:
                continue
            fitted += 1
            standard_stream = v35._sleeve(development, model, v34.STANDARD_COST, 0)
            cost_stream = v35._sleeve(development, model, v34.STRESS_COST, 0)
            delay_stream = v35._sleeve(development, model, v34.STANDARD_COST, 1)
            standard = _observe(development, standard_stream)
            cost = _observe(development, cost_stream)
            delay = _observe(development, delay_stream)
            definition = {
                "decision": decision,
                "exit": exit_bar,
                "universe": universe_name,
                "assets": assets,
                "ic_floor": ic_floor,
                "selection_mode": selection_mode,
                "weighting": weighting,
                "score_threshold": threshold,
                "factors": model.factors,
            }
            candidates.append(
                (
                    _rank(standard, cost, delay),
                    v12._identity(definition, "lev-v40o-"),
                    definition,
                    model,
                    standard_stream,
                    cost_stream,
                    delay_stream,
                )
            )
    candidates.sort(key=lambda item: item[0], reverse=True)
    candidates = candidates[: args.frontier]

    # Freeze the development frontier before historical and consumed diagnostics.
    historical = v34.Cube(args.root, "historical", 0)
    folds = np.array_split(np.flatnonzero(development.masks()["development_all"]), 5)
    records = []
    eligible = 0
    diagnostic_hits = 0
    for (
        rank,
        candidate_id,
        definition,
        model,
        standard_stream,
        cost_stream,
        delay_stream,
    ) in candidates:
        standard = _observe(development, standard_stream, True)
        cost = _observe(development, cost_stream, True)
        delay = _observe(development, delay_stream, True)
        historical_obs = _observe(
            historical,
            v35._sleeve(historical, model, v34.STANDARD_COST, 0),
            True,
        )["historical_2018_2020"]
        fold_obs = [
            metrics(
                standard_stream.values[index],
                standard_stream.benchmark[index],
                standard_stream.active[index],
            )
            for index in folds
        ]
        oos = standard["development_oos_2024_2025"]
        consumed = standard["consumed_2026_all"]
        z_score = float(oos["information_ratio"]) * math.sqrt(max(1, int(oos["trades"])) / 252)
        gates = {
            "standard_primary": v13._primary(standard),
            "cost_18bp_primary": v13._primary(cost),
            "delay_5min_primary": v13._primary(delay),
            "four_of_five_positive_folds": sum(
                float(item["annualized_return"]) > 0 for item in fold_obs
            )
            >= 4,
            "historical_positive_mdd_below_20pct": float(historical_obs["annualized_return"]) > 0
            and float(historical_obs["max_drawdown"]) < 0.20,
            "multiple_comparison_bonferroni_5pct": min(
                1.0, 2.0 * _normal_tail(abs(z_score)) * planned
            )
            < 0.05,
            "consumed_2026_total_above_20pct": float(consumed["total_return"]) > 0.20,
            "consumed_2026_mdd_below_20pct": float(consumed["max_drawdown"]) < 0.20,
            "consumed_2026_ir_at_least_1": float(consumed["information_ratio"]) >= 1.0,
            "ablation_evaluated": False,
            "start_date_stress_evaluated": False,
            "parameter_neighborhood_evaluated": False,
        }
        diagnostic_hits += int(
            gates["consumed_2026_total_above_20pct"]
            and gates["consumed_2026_mdd_below_20pct"]
            and gates["consumed_2026_ir_at_least_1"]
        )
        eligible += int(all(gates.values()))
        records.append(
            {
                "candidate_id": candidate_id,
                "definition": definition,
                "development_rank": list(rank),
                "standard": standard,
                "cost_18bp": cost,
                "delay_5min_9bp": delay,
                "historical_2018_2020": historical_obs,
                "folds": fold_obs,
                "gates": gates,
            }
        )
    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "selection_contract": "single daily multi-factor sleeve ranked on 2022-2025 only",
        "factor_version": v34.FACTOR_VERSION,
        "scan": {
            "planned_trials": planned,
            "fitted_trials": fitted,
            "frontier_size": len(records),
            "elapsed_seconds": time.perf_counter() - started,
        },
        "diagnostic_hits": diagnostic_hits,
        "eligible": eligible,
        "records": records,
    }
    v12._atomic(args.output, payload)
    print(json.dumps({key: payload[key] for key in ("scan", "diagnostic_hits", "eligible")}))
    if records:
        best = records[0]
        print(
            json.dumps(
                {
                    "candidate_id": best["candidate_id"],
                    "definition": best["definition"],
                    "development_rank": best["development_rank"],
                    "oos": best["standard"]["development_oos_2024_2025"],
                    "cost_oos": best["cost_18bp"]["development_oos_2024_2025"],
                    "delay_oos": best["delay_5min_9bp"]["development_oos_2024_2025"],
                    "consumed_2026": best["standard"]["consumed_2026_all"],
                    "historical": best["historical_2018_2020"],
                    "gates": best["gates"],
                }
            )
        )


if __name__ == "__main__":
    main()
