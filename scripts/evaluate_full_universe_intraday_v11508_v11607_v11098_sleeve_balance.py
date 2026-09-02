"""Fixed non-overlapping sleeve balances for parity-proven v11098."""

from __future__ import annotations

import argparse
import itertools
import json
import math
import time
from pathlib import Path

import evaluate_full_universe_intraday_v11307_v11406_v11098_portfolio_vol as base
import numpy as np
import pandas as pd

FIRST_VERSION = 11508
LAST_VERSION = 11607
PRIOR_COMPARISON_CELLS = 311_683
WEIGHTS = (0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95)


def specifications():
    return list(itertools.product(WEIGHTS, WEIGHTS))


def _weighted(openings, routes, outer, opening_weight, late_weight):
    return tuple(
        base.v34.v12.ReturnStream(
            opening.values * opening_weight + route.values * outer * late_weight,
            opening.benchmark * opening_weight + route.benchmark * outer * late_weight,
            opening.active | route.active,
            opening.component_trades + route.component_trades,
        )
        for opening, route in zip(openings, routes, strict=True)
    )


def _neighbor_share(cells, selected):
    left = WEIGHTS.index(selected["opening_weight"])
    right = WEIGHTS.index(selected["late_weight"])
    neighbors = [
        item
        for item in cells
        if abs(WEIGHTS.index(item["opening_weight"]) - left)
        + abs(WEIGHTS.index(item["late_weight"]) - right)
        <= 1
    ]
    return sum(item["primary"] for item in neighbors) / len(neighbors)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if len(specifications()) != 100:
        raise RuntimeError("V11508_PREREGISTRATION_MISMATCH")
    started = time.perf_counter()
    (
        development,
        historical,
        dev_openings,
        dev_routes,
        dev_outer,
        hist_openings,
        hist_routes,
        hist_outer,
    ) = base._base_streams(args.root, args.source, args.selection, return_components=True)
    cells = []
    for version, (opening_weight, late_weight) in enumerate(specifications(), start=FIRST_VERSION):
        dev_streams = _weighted(dev_openings, dev_routes, dev_outer, opening_weight, late_weight)
        hist_streams = _weighted(
            hist_openings, hist_routes, hist_outer, opening_weight, late_weight
        )
        observations = base._observe(development, dev_streams)
        cells.append(
            {
                "version": version,
                "opening_weight": opening_weight,
                "late_weight": late_weight,
                "streams": dev_streams,
                "observations": observations,
                "historical": tuple(
                    base.v47._observe(historical, stream, True)["historical_2018_2020"]
                    for stream in hist_streams
                ),
                "primary": all(base.passes_primary(item) for item in observations),
            }
        )
    total_cells = PRIOR_COMPARISON_CELLS + len(cells)
    folds = np.array_split(np.flatnonzero(development.masks()["development_all"]), 5)
    records = []
    for cell in cells:
        observations = cell["observations"]
        fold_metrics = {
            name: [
                base.metrics(stream.values[index], stream.benchmark[index], stream.active[index])
                for index in folds
            ]
            for name, stream in zip(
                ("standard", "cost_18bp", "delay_5min_9bp"),
                cell["streams"],
                strict=True,
            )
        }
        starts = {}
        for start in ("2022-01-01", "2023-01-01", "2024-01-01"):
            mask = development.masks()["development_all"] & (
                development.dates >= pd.Timestamp(start)
            )
            starts[start] = {
                name: base.metrics(stream.values[mask], stream.benchmark[mask], stream.active[mask])
                for name, stream in zip(
                    ("standard", "cost_18bp", "delay_5min_9bp"),
                    cell["streams"],
                    strict=True,
                )
            }
        neighborhood = _neighbor_share(cells, cell)
        oos = observations[0]["development_oos_2024_2025"]
        z_score = float(oos["information_ratio"]) * math.sqrt(max(1, int(oos["trades"])) / 252)
        gates = {
            "standard_primary": base.passes_primary(observations[0]),
            "cost_18bp_primary": base.passes_primary(observations[1]),
            "delay_5min_primary": base.passes_primary(observations[2]),
            "four_of_five_positive_folds_all_scenarios": all(
                sum(float(item["annualized_return"]) > 0 for item in values) >= 4
                for values in fold_metrics.values()
            ),
            "all_start_dates_positive_all_scenarios": all(
                float(item["annualized_return"]) > 0
                for scenario in starts.values()
                for item in scenario.values()
            ),
            "historical_15pct_mdd_below_20pct_all_scenarios": all(
                float(item["annualized_return"]) >= 0.15 and float(item["max_drawdown"]) < 0.20
                for item in cell["historical"]
            ),
            "parameter_neighborhood_70pct_primary": neighborhood >= 0.70,
            "consumed_2026q1_above_5pct": float(observations[0]["consumed_2026q1"]["total_return"])
            > 0.05,
            "consumed_2026_total_above_5pct": float(
                observations[0]["consumed_2026_all"]["total_return"]
            )
            > 0.05,
            "prospective_z_score_at_least_3": base.passes_global_evidence(z_score),
        }
        definition = {
            "version": cell["version"],
            "mechanism": "v11098_fixed_nonoverlap_sleeve_balance",
            "opening_weight": cell["opening_weight"],
            "late_weight": cell["late_weight"],
        }
        records.append(
            {
                "candidate_id": f"lev-v{cell['version']}-"
                + base.branch.boundary.logical.clock.parent.parent.sparse_veto.campaign._identity(
                    definition
                ),
                "definition": definition,
                "standard": observations[0],
                "cost_18bp": observations[1],
                "delay_5min_9bp": observations[2],
                "historical_scenarios": dict(
                    zip(
                        ("standard", "cost_18bp", "delay_5min_9bp"),
                        cell["historical"],
                        strict=True,
                    )
                ),
                "development_folds": fold_metrics,
                "start_date_stress": starts,
                "neighbor_primary_share": neighborhood,
                "multiple_comparison": {"total_cells": total_cells, "z_score": z_score},
                "gates": gates,
                "strict_pre_factory_null_pass": all(gates.values()),
            }
        )
    records.sort(
        key=lambda item: (
            item["strict_pre_factory_null_pass"],
            min(
                float(item[name]["development_oos_2024_2025"]["information_ratio"])
                for name in ("standard", "cost_18bp", "delay_5min_9bp")
            ),
        ),
        reverse=True,
    )
    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "version_range": [FIRST_VERSION, LAST_VERSION],
        "evaluated_cells": len(cells),
        "comparison_cells": total_cells,
        "strict_pre_factory_null_passes": sum(
            item["strict_pre_factory_null_pass"] for item in records
        ),
        "elapsed_seconds": time.perf_counter() - started,
        "records": records,
    }
    base.v34.v12._atomic(args.output, payload)
    print(
        json.dumps(
            {
                "status": payload["status"],
                "evaluated_cells": payload["evaluated_cells"],
                "strict_pre_factory_null_passes": payload["strict_pre_factory_null_passes"],
                "best": records[0]["candidate_id"],
                "elapsed_seconds": payload["elapsed_seconds"],
            }
        )
    )


if __name__ == "__main__":
    main()
