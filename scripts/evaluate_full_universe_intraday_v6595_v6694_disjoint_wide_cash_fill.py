"""v6595-v6694 disjoint wide-ensemble cash-fill campaign."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from pathlib import Path

import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v39_multifactor_regime_gate as v39
import evaluate_full_universe_intraday_v47_score_slope as v47
import evaluate_full_universe_intraday_v4070_v4169_state_routed_v42 as parent
import evaluate_full_universe_intraday_v4170_v4269_dual_parent_routing as dual
import evaluate_full_universe_intraday_v4470_v4569_early_quality_gate as route
import evaluate_full_universe_intraday_v6295_v6394_wide_diversification as wide
import evaluate_full_universe_intraday_v6395_v6494_cash_fill as cash
import numpy as np
import pandas as pd

from us_intraday_lab.fast_intraday_research import metrics

FIRST_VERSION = 6595
LAST_VERSION = 6694
PRIOR_COMPARISON_CELLS = 255_455
SOURCE_SHA256 = parent.SOURCE_SHA256
BASE_FAMILY = "breakout_quality"
BASE_QUANTILE = 0.0
BASE_ALPHA = 100.0


def specifications():
    return wide.campaign.specifications()


def _identity(definition: dict) -> str:
    payload = json.dumps(definition, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()[:16]


def _disjoint(base, fill):
    use_fill = (~base.active) & fill.active
    return v34.v12.ReturnStream(
        np.where(base.active, base.values, np.where(use_fill, fill.values, 0.0)),
        np.where(base.active, base.benchmark, np.where(use_fill, fill.benchmark, 0.0)),
        base.active | use_fill,
        base.component_trades + np.where(use_fill, fill.component_trades, 0),
    )


def _primary(observation):
    oos = observation["development_oos_2024_2025"]
    return (
        float(oos["annualized_return"]) >= 0.50
        and float(oos["max_drawdown"]) < 0.20
        and float(oos["information_ratio"]) >= 1.0
        and all(
            float(observation[name]["annualized_return"]) > 0
            for name in ("train_2022_2023", "2024", "2025")
        )
    )


def _rank(observations):
    return (
        min(
            float(item["development_oos_2024_2025"]["annualized_return"])
            for item in observations
        ),
        min(
            float(item["development_oos_2024_2025"]["information_ratio"])
            for item in observations
        ),
    )


def _base_streams(cube, cube_state, streams, core_model, override_model, gate_model):
    modern, _ = route._base_state(cube_state, core_model, override_model)
    score = route._score(cube, gate_model)
    allow = np.isfinite(score) & (score >= gate_model["threshold"])
    return route._route(streams, modern, allow)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if parent._sha(args.source) != SOURCE_SHA256:
        raise RuntimeError("V42_SOURCE_HASH_CHANGED")
    cash._configure()
    if len(specifications()) != 100:
        raise RuntimeError("DISJOINT_WIDE_PREREGISTRATION_MISMATCH")
    started = time.perf_counter()
    source = json.loads(args.source.read_text(encoding="utf-8"))
    records_by_id = {item["candidate_id"]: item for item in source["records"]}
    parent_ids = list(records_by_id)
    development = v34.Cube(args.root, "alpaca", 0)
    historical = v34.Cube(args.root, "historical", 0)
    development_state = parent.cross.Cube(args.root, "alpaca", 0)
    historical_state = parent.cross.Cube(args.root, "historical", 0)
    models = {
        candidate_id: v39._models(
            development, [records_by_id[candidate_id]["definition"]["strategy"]]
        )[0]
        for candidate_id in parent_ids
    }
    development_parents = {
        candidate_id: parent._parent_streams(
            development, records_by_id[candidate_id], models[candidate_id]
        )
        for candidate_id in parent_ids
    }
    historical_parents = {
        candidate_id: parent._parent_streams(
            historical, records_by_id[candidate_id], models[candidate_id]
        )
        for candidate_id in parent_ids
    }
    core_model = dual._fit_state(
        development_state, dual.STATE_FAMILIES["low_dispersion_trend"], 0.20
    )
    override_model = dual._fit_state(
        development_state, dual.STATE_FAMILIES["oversold_repair"], 0.35
    )
    _, transfer_state = route._base_state(development_state, core_model, override_model)
    gate_model = route._fit_gate(
        development,
        development_parents[route.TRANSFER_PARENT][0],
        transfer_state,
        route.FACTOR_SETS[BASE_FAMILY],
        BASE_QUANTILE,
        BASE_ALPHA,
    )
    base_ids = tuple(
        dict.fromkeys((route.MODERN_PARENT, route.TRANSFER_PARENT, cash.FALLBACK_PARENT))
    )
    dev_base = _base_streams(
        development,
        development_state,
        {item: development_parents[item] for item in base_ids},
        core_model,
        override_model,
        gate_model,
    )
    hist_base = _base_streams(
        historical,
        historical_state,
        {item: historical_parents[item] for item in base_ids},
        core_model,
        override_model,
        gate_model,
    )
    standard_streams = {
        candidate_id: streams[0] for candidate_id, streams in development_parents.items()
    }
    train = development.masks()["train_2022_2023"]
    cells = []
    for offset, (count, penalty, weighting, pool) in enumerate(specifications()):
        available = parent_ids[:100] if pool == "development_frontier_100" else parent_ids
        selected = wide.campaign._greedy(
            development, available, standard_streams, count, penalty, weighting
        )
        selected_dev = [
            [development_parents[item][scenario] for item in selected] for scenario in range(3)
        ]
        weights = wide.campaign._weights(selected_dev[0], train, weighting)
        fill_streams = tuple(
            wide.campaign._combine(items, weights) for items in selected_dev
        )
        streams = tuple(
            _disjoint(base, fill) for base, fill in zip(dev_base, fill_streams, strict=True)
        )
        observations = tuple(v47._observe(development, stream, True) for stream in streams)
        cells.append(
            {
                "version": FIRST_VERSION + offset,
                "count": count,
                "penalty": penalty,
                "weighting": weighting,
                "pool": pool,
                "selected": selected,
                "weights": weights,
                "streams": streams,
                "observations": observations,
                "primary": all(_primary(item) for item in observations),
            }
        )
    total_cells = PRIOR_COMPARISON_CELLS + len(cells)
    folds = np.array_split(np.flatnonzero(development.masks()["development_all"]), 5)
    results = []
    for cell in cells:
        selected_hist = [
            [historical_parents[item][scenario] for item in cell["selected"]]
            for scenario in range(3)
        ]
        historical_fill = tuple(
            wide.campaign._combine(items, cell["weights"]) for items in selected_hist
        )
        historical_streams = tuple(
            _disjoint(base, fill)
            for base, fill in zip(hist_base, historical_fill, strict=True)
        )
        historical_obs = tuple(
            v47._observe(historical, stream, True)["historical_2018_2020"]
            for stream in historical_streams
        )
        streams, observations = cell["streams"], cell["observations"]
        fold_metrics = {
            name: [
                metrics(stream.values[index], stream.benchmark[index], stream.active[index])
                for index in folds
            ]
            for name, stream in zip(
                ("standard", "cost_18bp", "delay_5min_9bp"), streams, strict=True
            )
        }
        starts = {}
        for start in ("2022-01-01", "2023-01-01", "2024-01-01"):
            mask = development.masks()["development_all"] & (
                development.dates >= pd.Timestamp(start)
            )
            starts[start] = metrics(
                streams[0].values[mask], streams[0].benchmark[mask], streams[0].active[mask]
            )
        count_index = wide.campaign.COUNTS.index(cell["count"])
        penalty_index = wide.campaign.PENALTIES.index(cell["penalty"])
        neighbors = [
            item
            for item in cells
            if item["weighting"] == cell["weighting"]
            and item["pool"] == cell["pool"]
            and abs(wide.campaign.COUNTS.index(item["count"]) - count_index)
            + abs(wide.campaign.PENALTIES.index(item["penalty"]) - penalty_index)
            <= 1
        ]
        neighborhood = sum(item["primary"] for item in neighbors) / len(neighbors)
        oos = observations[0]["development_oos_2024_2025"]
        z_score = float(oos["information_ratio"]) * math.sqrt(
            max(1, int(oos["trades"])) / 252
        )
        bonferroni = min(
            1.0, 2.0 * v47._normal_tail(abs(z_score)) * total_cells
        )
        gates = {
            "standard_primary": _primary(observations[0]),
            "cost_18bp_primary": _primary(observations[1]),
            "delay_5min_primary": _primary(observations[2]),
            "four_of_five_positive_folds_all_scenarios": all(
                sum(float(item["annualized_return"]) > 0 for item in values) >= 4
                for values in fold_metrics.values()
            ),
            "all_start_dates_positive": all(
                float(item["annualized_return"]) > 0 for item in starts.values()
            ),
            "historical_15pct_mdd_below_20pct_all_scenarios": all(
                float(item["annualized_return"]) >= 0.15
                and float(item["max_drawdown"]) < 0.20
                for item in historical_obs
            ),
            "parameter_neighborhood_70pct_primary": neighborhood >= 0.70,
            "consumed_2026q1_above_5pct": float(
                observations[0]["consumed_2026q1"]["total_return"]
            )
            > 0.05,
            "consumed_2026_total_above_5pct": float(
                observations[0]["consumed_2026_all"]["total_return"]
            )
            > 0.05,
            "cumulative_bonferroni_5pct": bonferroni < 0.05,
        }
        definition = {
            "version": cell["version"],
            "mechanism": "v6426_disjoint_wide_ensemble_cash_fill",
            "base_gate": {
                "factor_set": BASE_FAMILY,
                "quantile": BASE_QUANTILE,
                "alpha": BASE_ALPHA,
            },
            "fill_count": cell["count"],
            "correlation_penalty": cell["penalty"],
            "weighting": cell["weighting"],
            "pool": cell["pool"],
            "selected_parents": cell["selected"],
            "weights": cell["weights"].tolist(),
        }
        results.append(
            {
                "candidate_id": f"lev-v{cell['version']}-" + _identity(definition),
                "definition": definition,
                "standard": observations[0],
                "cost_18bp": observations[1],
                "delay_5min_9bp": observations[2],
                "historical_scenarios": dict(
                    zip(
                        ("standard", "cost_18bp", "delay_5min_9bp"),
                        historical_obs,
                        strict=True,
                    )
                ),
                "development_folds": fold_metrics,
                "start_date_stress": starts,
                "neighbor_primary_share": neighborhood,
                "multiple_comparison": {
                    "total_cells": total_cells,
                    "z_score": z_score,
                    "bonferroni_p": bonferroni,
                },
                "gates": gates,
                "strict_pre_factory_null_pass": all(gates.values()),
            }
        )
    results.sort(
        key=lambda item: _rank(
            (item["standard"], item["cost_18bp"], item["delay_5min_9bp"])
        ),
        reverse=True,
    )
    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "version_range": [FIRST_VERSION, LAST_VERSION],
        "evaluated_cells": len(results),
        "comparison_cells": total_cells,
        "elapsed_seconds": time.perf_counter() - started,
        "strict_pre_factory_null_passes": sum(
            item["strict_pre_factory_null_pass"] for item in results
        ),
        "records": results,
    }
    v34.v12._atomic(args.output, payload)
    print(
        json.dumps(
            {
                "status": payload["status"],
                "evaluated_cells": payload["evaluated_cells"],
                "strict_pre_factory_null_passes": payload[
                    "strict_pre_factory_null_passes"
                ],
                "best": results[0]["candidate_id"],
                "elapsed_seconds": payload["elapsed_seconds"],
            }
        )
    )


if __name__ == "__main__":
    main()
