"""Blend v11098 with development-ranked independent intraday sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from pathlib import Path

import evaluate_full_universe_intraday_v550_v649_state_gated_reversal as independent
import evaluate_full_universe_intraday_v5970_v6069_sector_flow_leadership as sector
import evaluate_full_universe_intraday_v11307_v11406_v11098_portfolio_vol as anchor
import numpy as np
import pandas as pd

FIRST_VERSION = 11608
LAST_VERSION = 11707
PRIOR_COMPARISON_CELLS = 311_783
INDEPENDENT_WEIGHTS = (0.05, 0.10, 0.15, 0.20, 0.25)
SOURCE_CONTRACTS = (
    (
        "v11207_v11306_opening_dislocation",
        "v11207_v11306_opening_dislocation_summary.json",
        "8a293d110297536cda6c58eb4ad5333bc23f121ba243166e4cb447fb4a2b80b0",
    ),
    (
        "v11408_v11507_midday_exhaustion_repair",
        "v11408_v11507_midday_exhaustion_repair_summary.json",
        "a9869265f754067882cdcf6a1b9b9cb6258143411bfb8eca26043bffb3b5de7f",
    ),
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _frozen_sources(artifact_root: Path) -> list[dict]:
    records = []
    for directory, summary_name, expected_sha in SOURCE_CONTRACTS:
        summary_path = artifact_root / summary_name
        if _sha(summary_path) != expected_sha:
            raise RuntimeError("V11608_SOURCE_SUMMARY_HASH_CHANGED")
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if summary.get("status") != "COMPLETE" or summary.get("completed_versions") != 100:
            raise RuntimeError("V11608_SOURCE_NOT_COMPLETE")
        paths = sorted((artifact_root / directory).glob("*.json"))
        if len(paths) != 100:
            raise RuntimeError("V11608_SOURCE_VERSION_COUNT_CHANGED")
        for path in paths:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("status") != "COMPLETE":
                raise RuntimeError("V11608_SOURCE_VERSION_INCOMPLETE")
            for item in payload["records"]:
                records.append(
                    {
                        "candidate_id": item["candidate_id"],
                        "definition": item["definition"],
                        "model": item["model"],
                        "development_rank": tuple(item["development_rank"]),
                    }
                )
    records.sort(key=lambda item: item["development_rank"], reverse=True)
    selected = records[:20]
    if len(selected) != 20 or len({item["candidate_id"] for item in selected}) != 20:
        raise RuntimeError("V11608_FROZEN_SELECTION_CHANGED")
    return selected


def _source_streams(cube, selected: dict):
    parameters = selected["definition"]
    model = selected["model"]
    streams = []
    for cost, delay in (
        (independent.prior.v34.STANDARD_COST, 0),
        (independent.prior.v34.STRESS_COST, 0),
        (independent.prior.v34.STANDARD_COST, 1),
    ):
        raw = independent.prior._rule_raw(
            cube,
            parameters,
            np.asarray(model["mean"]),
            np.asarray(model["scale"]),
            float(parameters["score_threshold"]),
            cost,
            delay,
        )
        if parameters["state_mode"] != "unfiltered":
            score = independent._state_score(
                cube,
                int(parameters["decision"]),
                model["state_means"],
                model["state_scales"],
            )
            allowed = np.isfinite(score) & (score >= float(parameters["state_threshold"]))
            raw = independent.prior._mask_stream(raw, allowed)
        streams.append(
            independent._scale(
                (raw,),
                float(parameters["target_volatility"]),
                int(parameters["lookback"]),
            )[0]
        )
    return tuple(streams)


def _blend(anchor_streams, source_streams, source_weight):
    anchor_weight = 1.0 - source_weight
    return tuple(
        anchor.v34.v12.ReturnStream(
            anchor_weight * left.values + source_weight * right.values,
            anchor_weight * left.benchmark + source_weight * right.benchmark,
            left.active | right.active,
            left.component_trades + right.component_trades,
        )
        for left, right in zip(anchor_streams, source_streams, strict=True)
    )


def _neighbor_share(cells, chosen):
    index = INDEPENDENT_WEIGHTS.index(chosen["source_weight"])
    neighbors = [
        cell
        for cell in cells
        if cell["source_id"] == chosen["source_id"]
        and abs(INDEPENDENT_WEIGHTS.index(cell["source_weight"]) - index) <= 1
    ]
    return sum(cell["primary"] for cell in neighbors) / len(neighbors)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--anchor-selection", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    sources = _frozen_sources(args.artifact_root)
    if len(sources) * len(INDEPENDENT_WEIGHTS) != 100:
        raise RuntimeError("V11608_PREREGISTRATION_MISMATCH")
    development, historical, anchor_dev, anchor_hist = anchor._base_streams(
        args.root, args.source, args.anchor_selection
    )
    source_dev_cube = sector.SectorFlowLeadershipCube(args.root, "alpaca", 0)
    source_hist_cube = sector.SectorFlowLeadershipCube(args.root, "historical", 0)
    if not np.array_equal(development.dates, source_dev_cube.dates) or not np.array_equal(
        historical.dates, source_hist_cube.dates
    ):
        raise RuntimeError("V11608_DATE_AXIS_MISMATCH")
    cells = []
    version = FIRST_VERSION
    for source in sources:
        source_dev = _source_streams(source_dev_cube, source)
        source_hist = _source_streams(source_hist_cube, source)
        for source_weight in INDEPENDENT_WEIGHTS:
            dev_streams = _blend(anchor_dev, source_dev, source_weight)
            hist_streams = _blend(anchor_hist, source_hist, source_weight)
            observations = anchor._observe(development, dev_streams)
            cells.append(
                {
                    "version": version,
                    "source_id": source["candidate_id"],
                    "source_weight": source_weight,
                    "streams": dev_streams,
                    "observations": observations,
                    "historical": tuple(
                        anchor.v47._observe(historical, stream, True)["historical_2018_2020"]
                        for stream in hist_streams
                    ),
                    "primary": all(anchor.passes_primary(item) for item in observations),
                }
            )
            version += 1
    total_cells = PRIOR_COMPARISON_CELLS + len(cells)
    folds = np.array_split(np.flatnonzero(development.masks()["development_all"]), 5)
    records = []
    for cell in cells:
        observations = cell["observations"]
        fold_metrics = {
            name: [
                anchor.metrics(stream.values[index], stream.benchmark[index], stream.active[index])
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
                name: anchor.metrics(
                    stream.values[mask], stream.benchmark[mask], stream.active[mask]
                )
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
            "standard_primary": anchor.passes_primary(observations[0]),
            "cost_18bp_primary": anchor.passes_primary(observations[1]),
            "delay_5min_primary": anchor.passes_primary(observations[2]),
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
            "prospective_z_score_at_least_3": anchor.passes_global_evidence(z_score),
        }
        definition = {
            "version": cell["version"],
            "mechanism": "v11098_development_ranked_independent_blend",
            "source_candidate": cell["source_id"],
            "source_weight": cell["source_weight"],
            "anchor_weight": 1.0 - cell["source_weight"],
        }
        records.append(
            {
                "candidate_id": f"lev-v{cell['version']}-"
                + anchor.branch.boundary.logical.clock.parent.parent.sparse_veto.campaign._identity(
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
        "selected_source_ids": [item["candidate_id"] for item in sources],
        "strict_pre_factory_null_passes": sum(
            item["strict_pre_factory_null_pass"] for item in records
        ),
        "elapsed_seconds": time.perf_counter() - started,
        "records": records,
    }
    anchor.v34.v12._atomic(args.output, payload)
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
