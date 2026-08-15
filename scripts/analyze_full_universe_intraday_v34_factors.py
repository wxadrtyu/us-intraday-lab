"""Multi-period factor audit for the v34 causal minute-path factor pool."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v35_rank_ensemble as v35
import numpy as np
import search_full_universe_intraday_v12_robustness as v12

PERIODS = ("train_2022_2023", "2024", "2025")


def _factor_result(values: np.ndarray, label: np.ndarray, finite: np.ndarray, period: np.ndarray):
    selected = period[:, None] & finite & np.isfinite(values)
    ic = v35._spearman(values[selected], label[selected])
    long_returns = []
    for row in np.flatnonzero(period):
        valid = finite[row] & np.isfinite(values[row]) & np.isfinite(label[row])
        if valid.sum() < 2:
            continue
        local = np.flatnonzero(valid)[np.argmax(values[row, valid])]
        long_returns.append(float(label[row, local]))
    if not long_returns:
        return {"ic": ic, "long_annualized": float("nan"), "observations": 0}
    returns = np.asarray(long_returns)
    annualized = float(np.prod(1.0 + returns) ** (252.0 / len(returns)) - 1.0)
    return {"ic": ic, "long_annualized": annualized, "observations": len(returns)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    cube = v34.Cube(args.root, "alpaca", 0)
    masks = cube.masks()
    all_factors = tuple(
        dict.fromkeys(factor for group in v34.FACTOR_GROUPS.values() for factor in group)
    )
    audits = []
    for profile_name, profile in v34.PROFILES.items():
        for slot, assets in zip(v34.SCHEDULE, profile, strict=True):
            specification = {**slot, "assets": assets}
            matrix, label, finite = v34._matrix(cube, specification, all_factors)
            factor_results = {}
            for factor_index, factor in enumerate(all_factors):
                factor_results[factor] = {
                    period: _factor_result(matrix[:, :, factor_index], label, finite, masks[period])
                    for period in PERIODS
                }
            stable = []
            for factor, observations in factor_results.items():
                ics = [float(observations[period]["ic"]) for period in PERIODS]
                if all(np.isfinite(ics)) and min(ics) > 0:
                    stable.append({"factor": factor, "direction": 1, "minimum_abs_ic": min(ics)})
                elif all(np.isfinite(ics)) and max(ics) < 0:
                    stable.append(
                        {
                            "factor": factor,
                            "direction": -1,
                            "minimum_abs_ic": min(abs(x) for x in ics),
                        }
                    )
            stable.sort(key=lambda item: float(item["minimum_abs_ic"]), reverse=True)
            audits.append(
                {
                    "profile": profile_name,
                    "slot": slot["name"],
                    "decision": slot["decision"],
                    "exit": slot["exit"],
                    "assets": assets,
                    "factors": factor_results,
                    "stable_all_periods": stable,
                }
            )
    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "selection_contract": "factor audit uses 2022-2025 only; consumed 2026 is not read",
        "factor_version": v34.FACTOR_VERSION,
        "factor_groups": v34.FACTOR_GROUPS,
        "periods": PERIODS,
        "audit_count": len(audits),
        "elapsed_seconds": time.perf_counter() - started,
        "audits": audits,
    }
    v12._atomic(args.output, payload)
    summary = [
        {
            "profile": item["profile"],
            "slot": item["slot"],
            "stable": item["stable_all_periods"][:8],
        }
        for item in audits
    ]
    print(
        json.dumps(
            {
                "audit_count": len(audits),
                "elapsed_seconds": payload["elapsed_seconds"],
                "summary": summary,
            }
        )
    )


if __name__ == "__main__":
    main()
