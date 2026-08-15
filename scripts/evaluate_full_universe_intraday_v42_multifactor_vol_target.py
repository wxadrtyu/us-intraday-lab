"""Causal volatility targeting for the frozen low-turnover multi-factor frontier."""

from __future__ import annotations

import argparse
import itertools
import json
import math
import time
from pathlib import Path

import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v35_rank_ensemble as v35
import evaluate_full_universe_intraday_v39_multifactor_regime_gate as v39
import numpy as np
import search_full_universe_intraday_v12_robustness as v12
import search_full_universe_intraday_v13_regime_rotation as v13
import search_full_universe_intraday_v15_prior5 as v15

from us_intraday_lab.fast_intraday_research import metrics

LOOKBACKS = (20, 40, 60)
TARGET_VOLATILITIES = (0.15, 0.20, 0.25, 0.30, 0.40)
MIN_EXPOSURES = (0.0, 0.25)


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


def _exposure(values: np.ndarray, lookback: int, target: float, minimum: float):
    output = np.ones(len(values))
    for index in range(lookback, len(values)):
        realized = float(np.std(values[index - lookback : index], ddof=1) * np.sqrt(252.0))
        if np.isfinite(realized) and realized > 1e-8:
            output[index] = np.clip(target / realized, minimum, 1.0)
    return output


def _scaled(stream: v12.ReturnStream, exposure: np.ndarray):
    active = stream.active & (exposure > 0)
    return v12.ReturnStream(
        stream.values * exposure,
        stream.benchmark * exposure,
        active,
        np.where(active, stream.component_trades, 0),
    )


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
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--parents", default=200, type=int)
    parser.add_argument("--frontier", default=500, type=int)
    args = parser.parse_args()
    started = time.perf_counter()
    source = json.loads(args.source.read_text(encoding="utf-8"))
    parents = source["records"][: args.parents]
    development = v34.Cube(args.root, "alpaca", 0)
    candidates = []
    scanned = 0
    model_cache = {}
    stream_cache = {}
    for parent in parents:
        model = v39._models(development, [parent["definition"]])[0]
        model_cache[parent["candidate_id"]] = model
        streams = (
            v35._sleeve(development, model, v34.STANDARD_COST, 0),
            v35._sleeve(development, model, v34.STRESS_COST, 0),
            v35._sleeve(development, model, v34.STANDARD_COST, 1),
        )
        stream_cache[parent["candidate_id"]] = streams
        for lookback, target, minimum in itertools.product(
            LOOKBACKS, TARGET_VOLATILITIES, MIN_EXPOSURES
        ):
            scanned += 1
            exposure = _exposure(streams[0].values, lookback, target, minimum)
            scaled = [_scaled(stream, exposure) for stream in streams]
            observations = [_observe(development, stream) for stream in scaled]
            definition = {
                "parent_id": parent["candidate_id"],
                "strategy": parent["definition"],
                "lookback": lookback,
                "target_volatility": target,
                "minimum_exposure": minimum,
            }
            candidates.append(
                (
                    _rank(*observations),
                    v12._identity(definition, "lev-v42t-"),
                    definition,
                )
            )
    candidates.sort(key=lambda item: item[0], reverse=True)
    candidates = candidates[: args.frontier]

    # Freeze all development choices before historical and consumed diagnostics.
    historical = v34.Cube(args.root, "historical", 0)
    folds = np.array_split(np.flatnonzero(development.masks()["development_all"]), 5)
    historical_cache = {}
    records = []
    eligible = 0
    diagnostic_hits = 0
    for rank, candidate_id, definition in candidates:
        parent_id = definition["parent_id"]
        streams = stream_cache[parent_id]
        exposure = _exposure(
            streams[0].values,
            int(definition["lookback"]),
            float(definition["target_volatility"]),
            float(definition["minimum_exposure"]),
        )
        scaled = [_scaled(stream, exposure) for stream in streams]
        standard, cost, delay = [_observe(development, stream, True) for stream in scaled]
        if parent_id not in historical_cache:
            historical_cache[parent_id] = v35._sleeve(
                historical, model_cache[parent_id], v34.STANDARD_COST, 0
            )
        historical_stream = historical_cache[parent_id]
        historical_exposure = _exposure(
            historical_stream.values,
            int(definition["lookback"]),
            float(definition["target_volatility"]),
            float(definition["minimum_exposure"]),
        )
        historical_obs = _observe(
            historical, _scaled(historical_stream, historical_exposure), True
        )["historical_2018_2020"]
        fold_obs = [
            metrics(stream.values[index], stream.benchmark[index], stream.active[index])
            for index in folds
            for stream in scaled[:1]
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
                1.0, 2.0 * _normal_tail(abs(z_score)) * scanned
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
        "selection_contract": "causal exposure controls ranked on 2022-2025 only",
        "factor_version": v34.FACTOR_VERSION,
        "scan": {
            "parents": len(parents),
            "trials": scanned,
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
