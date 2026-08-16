"""Audit factors conditional on the frozen v45 event trigger without reading 2026."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import analyze_full_universe_intraday_v53_cross_asset_factors as v53
import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v35_rank_ensemble as v35
import evaluate_full_universe_intraday_v44_multihorizon_confirmation as v44
import numpy as np
import search_full_universe_intraday_v12_robustness as v12
import validate_full_universe_intraday_v46_factory_null as v46

PERIODS = ("train_2022_2023", "2024", "2025")
DEFINITION = {
    "horizons": (20, 23, 26, 29),
    "exit": 72,
    "weighting": "reliability",
    "score_threshold": 0.75,
    "confirmations": 2,
}
FACTORS = tuple(dict.fromkeys((*v34.FACTOR_GROUPS["structure"], *v53.NEW_FACTORS)))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    cube = v53.Cube(args.root, "alpaca", 0)
    models = v44._fit(cube, DEFINITION["horizons"], DEFINITION["exit"])
    selected, decision = v46._trigger(
        cube,
        models,
        DEFINITION["exit"],
        DEFINITION["weighting"],
        DEFINITION["score_threshold"],
        DEFINITION["confirmations"],
        None,
    )
    active = selected >= 0
    entry = decision + 1
    safe_asset = np.maximum(selected, 0)
    safe_entry = np.maximum(entry, 0)
    label = np.full(len(cube.sessions), np.nan)
    label[active] = (
        cube.opens[cube.rows[active], DEFINITION["exit"], safe_asset[active]]
        / cube.opens[cube.rows[active], safe_entry[active], safe_asset[active]]
        - 1.0
        - v34.STANDARD_COST
    )
    factor_values = {name: np.full(len(cube.sessions), np.nan) for name in FACTORS}
    for horizon in DEFINITION["horizons"]:
        rows = np.flatnonzero(active & (decision == horizon))
        available = cube.factors(horizon)
        for name in FACTORS:
            factor_values[name][rows] = available[name][rows, safe_asset[rows]]
    masks = cube.masks()
    results = {}
    stable = []
    stable_by_asset = {}
    for name, values in factor_values.items():
        periods = {}
        for period in PERIODS:
            valid = masks[period] & active & np.isfinite(values) & np.isfinite(label)
            periods[period] = {
                "ic": v35._spearman(values[valid], label[valid]),
                "triggers": int(valid.sum()),
            }
        results[name] = periods
        ics = [float(periods[period]["ic"]) for period in PERIODS]
        if all(np.isfinite(ics)) and min(ics) > 0:
            stable.append({"factor": name, "direction": 1, "minimum_abs_ic": min(ics)})
        elif all(np.isfinite(ics)) and max(ics) < 0:
            stable.append(
                {
                    "factor": name,
                    "direction": -1,
                    "minimum_abs_ic": min(abs(value) for value in ics),
                }
            )
    for asset in v44.ASSETS:
        symbol = v12.SYMBOLS[asset]
        asset_stable = []
        for name, values in factor_values.items():
            ics = []
            for period in PERIODS:
                valid = (
                    masks[period]
                    & active
                    & (selected == asset)
                    & np.isfinite(values)
                    & np.isfinite(label)
                )
                ics.append(v35._spearman(values[valid], label[valid]))
            if all(np.isfinite(ics)) and min(ics) > 0:
                asset_stable.append({"factor": name, "direction": 1, "minimum_abs_ic": min(ics)})
            elif all(np.isfinite(ics)) and max(ics) < 0:
                asset_stable.append(
                    {
                        "factor": name,
                        "direction": -1,
                        "minimum_abs_ic": min(abs(value) for value in ics),
                    }
                )
        asset_stable.sort(key=lambda item: float(item["minimum_abs_ic"]), reverse=True)
        stable_by_asset[symbol] = asset_stable
    stable.sort(key=lambda item: float(item["minimum_abs_ic"]), reverse=True)
    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "selection_contract": "conditional factor audit uses 2022-2025 only; 2026 is not read",
        "base_definition": DEFINITION,
        "factors": results,
        "stable_all_periods": stable,
        "stable_by_asset": stable_by_asset,
        "scan": {
            "factors": len(FACTORS),
            "event_triggers": int((active & masks["development_all"]).sum()),
            "elapsed_seconds": time.perf_counter() - started,
        },
    }
    v12._atomic(args.output, payload)
    print(
        json.dumps(
            {
                "scan": payload["scan"],
                "stable_all_periods": stable,
                "stable_by_asset": stable_by_asset,
            }
        )
    )


if __name__ == "__main__":
    main()
