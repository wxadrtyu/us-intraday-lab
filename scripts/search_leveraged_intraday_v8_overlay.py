"""Causal trailing-performance overlay for the frozen v7 return stream."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from us_intraday_lab.fast_intraday_research import metrics


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _trailing(values: np.ndarray, lookback: int) -> np.ndarray:
    result = np.full(len(values), np.nan)
    logs = np.log1p(values)
    cumulative = np.concatenate([[0.0], np.cumsum(logs)])
    for index in range(lookback, len(values)):
        result[index] = np.expm1(cumulative[index] - cumulative[index - lookback])
    return result


def _evaluate(
    values: np.ndarray,
    benchmark: np.ndarray,
    underlying_active: np.ndarray,
    enabled: np.ndarray,
    mask: np.ndarray,
) -> dict[str, float | int]:
    active = underlying_active & enabled
    return metrics(np.where(enabled, values, 0.0)[mask], benchmark[mask], active[mask])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--development", required=True, type=Path)
    parser.add_argument("--final", required=True, type=Path)
    parser.add_argument(
        "--final-scenario",
        default="cost_1_5x_next_bar_open",
        choices=(
            "cost_1_5x_next_bar_open",
            "cost_2x_next_bar_open",
            "cost_1_5x_one_bar_delay",
            "cost_2x_one_bar_delay",
        ),
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    development = json.loads(args.development.read_text(encoding="utf-8"))["requested_daily"]
    final = json.loads(args.final.read_text(encoding="utf-8"))["scenarios"][args.final_scenario][
        "daily"
    ]
    sessions = pd.to_datetime(development["sessions"] + final["sessions"])
    values = np.array(development["returns"] + final["returns"], dtype=float)
    benchmark = np.array(development["benchmark_returns"] + final["benchmark_returns"], dtype=float)
    underlying_active = np.array(development["active"] + final["active"], dtype=bool)
    years = sessions.year.to_numpy()
    masks = {
        "train": years <= 2023,
        "2024": years == 2024,
        "2025": years == 2025,
        "development_oos": (years == 2024) | (years == 2025),
        "consumed_2026q1_diagnostic": years == 2026,
        "aggregate_diagnostic": years >= 2024,
    }
    records: list[dict[str, Any]] = []
    for fast, slow, fast_floor, slow_floor in itertools.product(
        (5, 10, 20, 40),
        (20, 40, 60, 90),
        (-0.05, -0.025, 0.0, 0.025, 0.05),
        (-0.10, -0.05, -0.025, 0.0, 0.025, 0.05),
    ):
        if fast >= slow:
            continue
        fast_return = _trailing(values, fast)
        slow_return = _trailing(values, slow)
        enabled = (fast_return >= fast_floor) & (slow_return >= slow_floor)
        observations = {
            name: _evaluate(values, benchmark, underlying_active, enabled, mask)
            for name, mask in masks.items()
        }
        parameters = {
            "fast_lookback": fast,
            "slow_lookback": slow,
            "fast_return_floor": fast_floor,
            "slow_return_floor": slow_floor,
        }
        identity = json.dumps(parameters, sort_keys=True, separators=(",", ":"))
        record = {
            "candidate_id": "lev-v8-" + hashlib.sha256(identity.encode()).hexdigest()[:16],
            "parameters": parameters,
            **observations,
        }
        record["weakest_development_annualized_return"] = min(
            float(observations[name]["annualized_return"]) for name in ("train", "2024", "2025")
        )
        records.append(record)
    records.sort(
        key=lambda item: (
            float(item["weakest_development_annualized_return"]),
            float(item["development_oos"]["annualized_return"]),
            float(item["development_oos"]["information_ratio"]),
        ),
        reverse=True,
    )
    target = [
        item
        for item in records
        if float(item["development_oos"]["annualized_return"]) >= 0.50
        and float(item["development_oos"]["max_drawdown"]) < 0.20
        and float(item["development_oos"]["information_ratio"]) >= 1.0
        and float(item["train"]["annualized_return"]) > 0.0
        and float(item["2024"]["annualized_return"]) > 0.0
        and float(item["2025"]["annualized_return"]) > 0.0
    ]
    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "selection_contract": "parameters are ranked on 2022-2025 only",
        "warning": "2026Q1 was previously consumed by v7 and is reported only as a diagnostic",
        "final_scenario": args.final_scenario,
        "scanned": len(records),
        "target_hit_count": len(target),
        "target_hits": target[:100],
        "frontier": records[:100],
    }
    _write(args.output, payload)
    print(
        json.dumps(
            {
                "scanned": len(records),
                "target_hits": len(target),
                "best": records[0] if records else None,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
