"""v146-v245: development-ranked sleeves anchored to frozen v45 at gross one."""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import analyze_full_universe_intraday_v53_cross_asset_factors as v53
import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v42_multifactor_vol_target as v42
import evaluate_full_universe_intraday_v44_multihorizon_confirmation as v44
import evaluate_full_universe_intraday_v45_event_trigger_multifactor as v45
import evaluate_full_universe_intraday_v47_score_slope as v47
import evaluate_full_universe_intraday_v59_v145_version_campaign as campaign
import numpy as np
import search_full_universe_intraday_v12_robustness as v12
import search_full_universe_intraday_v13_regime_rotation as v13

from us_intraday_lab.fast_intraday_research import metrics

V45_WEIGHTS = (0.50, 0.60, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95)
TOP_PER_VERSION = 5
CUMULATIVE_COMPARISON_CELLS = 12_400 + 15_660 + 100 * len(V45_WEIGHTS)


def _ridge_model(record: dict) -> campaign.RidgeModel:
    definition = record["definition"]
    model = record["model"]
    negative = model["negative_coefficients"]
    return campaign.RidgeModel(
        tuple(definition["factors"]),
        int(definition["decision"]),
        int(definition["exit"]),
        float(definition["alpha"]),
        np.asarray(model["mean"]),
        np.asarray(model["scale"]),
        np.asarray(model["coefficients"]),
        np.asarray(negative) if negative is not None else None,
        float(model["threshold"]),
    )


def _component_streams(cube: v53.Cube, record: dict):
    definition = record["definition"]
    return campaign._streams(
        cube,
        _ridge_model(record),
        str(definition["engine"]),
        float(definition["target_volatility"]),
        int(definition["lookback"]),
    )


def _v45_streams(cube: v53.Cube, models):
    raw = (
        v45._stream(cube, models, 72, "reliability", 0.75, 2, v34.STANDARD_COST, 0),
        v45._stream(cube, models, 72, "reliability", 0.75, 2, v34.STRESS_COST, 0),
        v45._stream(cube, models, 72, "reliability", 0.75, 2, v34.STANDARD_COST, 1),
    )
    exposure = v42._exposure(raw[0].values, 15, 0.35, 0.0)
    return tuple(v42._scaled(stream, exposure) for stream in raw)


def _blend(anchor: v12.ReturnStream, component: v12.ReturnStream, weight: float):
    return v12.ReturnStream(
        weight * anchor.values + (1.0 - weight) * component.values,
        weight * anchor.benchmark + (1.0 - weight) * component.benchmark,
        anchor.active | component.active,
        anchor.component_trades + component.component_trades,
    )


def _development_components(source_dir: Path) -> list[dict]:
    records = []
    for version in range(59, 146):
        payload = json.loads(
            (source_dir / f"full-universe-intraday-v{version}-exact.json").read_text(
                encoding="utf-8"
            )
        )
        records.extend(payload["records"])
    records.sort(key=lambda item: tuple(item["development_rank"]), reverse=True)
    selected = records[:100]
    if len(selected) != 100:
        raise RuntimeError("anchored ensemble requires 100 development-ranked components")
    return selected


def _version_path(output_dir: Path, version: int) -> Path:
    return output_dir / f"full-universe-intraday-v{version}-exact.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    development = v53.Cube(args.root, "alpaca", 0)
    historical = v53.Cube(args.root, "historical", 0)
    components = _development_components(args.source_dir)
    anchor_models = v44._fit(development, (20, 23, 26, 29), 72)
    anchor_development = _v45_streams(development, anchor_models)
    anchor_historical = _v45_streams(historical, anchor_models)[0]
    folds = np.array_split(np.flatnonzero(development.masks()["development_all"]), 5)
    summaries = []
    total_hits = 0
    for index, component_record in enumerate(components):
        version = 146 + index
        version_started = time.perf_counter()
        component_development = _component_streams(development, component_record)
        component_historical = _component_streams(historical, component_record)[0]
        cells = []
        for weight in V45_WEIGHTS:
            streams = tuple(
                _blend(anchor, component, weight)
                for anchor, component in zip(anchor_development, component_development, strict=True)
            )
            observations = [v47._observe(development, stream) for stream in streams]
            definition = {
                "version": version,
                "strategy": "v45_anchored_multifactor_ensemble",
                "anchor_candidate_id": "lev-v45e-0d302fbf92727a31",
                "component_candidate_id": component_record["candidate_id"],
                "component_definition": component_record["definition"],
                "v45_weight": weight,
                "component_weight": 1.0 - weight,
                "maximum_gross": 1.0,
            }
            cells.append(
                {
                    "definition": definition,
                    "streams": streams,
                    "observations": observations,
                    "rank": v47._rank(*observations),
                }
            )
        cells.sort(key=lambda item: item["rank"], reverse=True)
        records = []
        version_hits = 0
        for item in cells[:TOP_PER_VERSION]:
            definition = item["definition"]
            weight = float(definition["v45_weight"])
            streams = item["streams"]
            standard, cost, delay = [v47._observe(development, stream, True) for stream in streams]
            historical_stream = _blend(anchor_historical, component_historical, weight)
            historical_obs = v47._observe(historical, historical_stream, True)[
                "historical_2018_2020"
            ]
            fold_obs = [
                metrics(
                    streams[0].values[fold],
                    streams[0].benchmark[fold],
                    streams[0].active[fold],
                )
                for fold in folds
            ]
            position = V45_WEIGHTS.index(weight)
            neighbor_weights = V45_WEIGHTS[
                max(0, position - 1) : min(len(V45_WEIGHTS), position + 2)
            ]
            neighbor_cells = [
                cell
                for cell in cells
                if float(cell["definition"]["v45_weight"]) in neighbor_weights
            ]
            neighbor_share = sum(
                float(cell["observations"][0]["development_oos_2024_2025"]["annualized_return"]) > 0
                for cell in neighbor_cells
            ) / len(neighbor_cells)
            oos = standard["development_oos_2024_2025"]
            consumed = standard["consumed_2026_all"]
            z_score = float(oos["information_ratio"]) * math.sqrt(max(1, int(oos["trades"])) / 252)
            gates = {
                "standard_primary": v13._primary(standard),
                "cost_18bp_primary": v13._primary(cost),
                "delay_5min_primary": v13._primary(delay),
                "four_of_five_positive_folds": sum(
                    float(value["annualized_return"]) > 0 for value in fold_obs
                )
                >= 4,
                "historical_positive_mdd_below_20pct": float(historical_obs["annualized_return"])
                > 0
                and float(historical_obs["max_drawdown"]) < 0.20,
                "parameter_neighborhood_75pct_positive": neighbor_share >= 0.75,
                "cumulative_bonferroni_5pct": min(
                    1.0,
                    2.0 * v47._normal_tail(abs(z_score)) * CUMULATIVE_COMPARISON_CELLS,
                )
                < 0.05,
                "consumed_2026_total_above_5pct": float(consumed["total_return"]) > 0.05,
            }
            pre_null_names = (
                "standard_primary",
                "cost_18bp_primary",
                "delay_5min_primary",
                "four_of_five_positive_folds",
                "historical_positive_mdd_below_20pct",
                "parameter_neighborhood_75pct_positive",
                "consumed_2026_total_above_5pct",
            )
            pre_null = all(gates[name] for name in pre_null_names)
            version_hits += int(pre_null)
            total_hits += int(pre_null)
            records.append(
                {
                    "candidate_id": f"lev-v{version}-" + campaign._identity(definition)[:16],
                    "definition": definition,
                    "development_rank": list(item["rank"]),
                    "standard": standard,
                    "cost_18bp": cost,
                    "delay_5min_9bp": delay,
                    "historical_2018_2020": historical_obs,
                    "folds": fold_obs,
                    "neighbor_positive_share": neighbor_share,
                    "gates": gates,
                    "pre_factory_null_pass": pre_null,
                }
            )
        payload = {
            "schema_version": "1.0.0",
            "status": "COMPLETE",
            "version": version,
            "selection_contract": (
                "component is selected only from the globally development-ranked v59-v145 "
                "frontier; ensemble weight is ranked before historical and consumed-2026 "
                "diagnostics; maximum gross remains one"
            ),
            "cumulative_multiple_comparison_cells": CUMULATIVE_COMPARISON_CELLS,
            "scan": {
                "planned_cells": len(V45_WEIGHTS),
                "evaluated_cells": len(cells),
                "frozen_frontier": len(records),
                "elapsed_seconds": time.perf_counter() - version_started,
            },
            "pre_factory_null_hits": version_hits,
            "records": records,
        }
        v12._atomic(_version_path(args.output_dir, version), payload)
        best = records[0]
        summaries.append(
            {
                "version": version,
                "component_candidate_id": component_record["candidate_id"],
                "pre_factory_null_hits": version_hits,
                "best_candidate_id": best["candidate_id"],
                "best_oos_annualized_return": best["standard"]["development_oos_2024_2025"][
                    "annualized_return"
                ],
                "best_consumed_2026_total_return": best["standard"]["consumed_2026_all"][
                    "total_return"
                ],
            }
        )
        v12._atomic(
            args.summary,
            {
                "schema_version": "1.0.0",
                "status": "RUNNING" if index < 99 else "COMPLETE",
                "version_range": [146, 245],
                "planned_versions": 100,
                "completed_versions": index + 1,
                "cumulative_multiple_comparison_cells": CUMULATIVE_COMPARISON_CELLS,
                "pre_factory_null_hits": total_hits,
                "elapsed_seconds": time.perf_counter() - started,
                "versions": summaries,
            },
        )
        print(
            json.dumps(
                {
                    "progress": f"{index + 1}/100",
                    "version": version,
                    "pre_factory_null_hits": version_hits,
                    "total_hits": total_hits,
                    "best_oos_annualized_return": summaries[-1]["best_oos_annualized_return"],
                    "best_consumed_2026_total_return": summaries[-1][
                        "best_consumed_2026_total_return"
                    ],
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
