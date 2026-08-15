"""Focused falsification of the v42 low-turnover multi-factor candidate."""

from __future__ import annotations

import argparse
import itertools
import json
import time
from dataclasses import replace
from pathlib import Path

import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v35_rank_ensemble as v35
import evaluate_full_universe_intraday_v38_multifactor_sleeve_beam as v38
import evaluate_full_universe_intraday_v39_multifactor_regime_gate as v39
import evaluate_full_universe_intraday_v42_multifactor_vol_target as v42
import numpy as np
import search_full_universe_intraday_v12_robustness as v12
import search_full_universe_intraday_v13_regime_rotation as v13

from us_intraday_lab.fast_intraday_research import metrics

DECISIONS = (20, 23, 26)
EXITS = (69, 72, 75)
THRESHOLDS = (0.25, 0.50, 0.75)
TARGETS = (0.25, 0.30, 0.35)
LOOKBACKS = (15, 20, 25)
START_DATES = ("2022-01-01", "2022-07-01", "2023-01-01", "2023-07-01", "2024-01-01")


def _streams(cube: v34.Cube, model: v35.RankModel):
    return (
        v35._sleeve(cube, model, v34.STANDARD_COST, 0),
        v35._sleeve(cube, model, v34.STRESS_COST, 0),
        v35._sleeve(cube, model, v34.STANDARD_COST, 1),
    )


def _scaled_streams(streams, lookback: int, target: float):
    exposure = v42._exposure(streams[0].values, lookback, target, 0.0)
    return tuple(v42._scaled(stream, exposure) for stream in streams)


def _observe(cube: v34.Cube, stream: v12.ReturnStream):
    return v42._observe(cube, stream, True)


def _start_date_metrics(cube: v34.Cube, stream: v12.ReturnStream):
    sessions = np.asarray(cube.sessions.values, dtype="datetime64[D]")
    end = np.datetime64("2025-12-31")
    output = {}
    for start_text in START_DATES:
        mask = (sessions >= np.datetime64(start_text)) & (sessions <= end)
        output[start_text] = metrics(
            stream.values[mask], stream.benchmark[mask], stream.active[mask]
        )
    return output


def _model(cube: v34.Cube, definition: dict, decision: int, exit_bar: int, threshold: float):
    strategy = definition["strategy"]
    specification = {
        "name": "daily_once",
        "decision": decision,
        "exit": exit_bar,
        "assets": tuple(strategy["assets"]),
    }
    matrix, finite, diagnostics = v38._diagnostics(cube, specification)
    return v38._model(
        cube,
        specification,
        matrix,
        finite,
        diagnostics,
        float(strategy["ic_floor"]),
        str(strategy["selection_mode"]),
        str(strategy["weighting"]),
        threshold,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    source = json.loads(args.source.read_text(encoding="utf-8"))
    record = next(item for item in source["records"] if item["candidate_id"] == args.candidate)
    definition = record["definition"]
    development = v34.Cube(args.root, "alpaca", 0)
    base_model = v39._models(development, [definition["strategy"]])[0]
    base_streams = _scaled_streams(
        _streams(development, base_model),
        int(definition["lookback"]),
        float(definition["target_volatility"]),
    )

    ablations = []
    for dropped in base_model.factors:
        keep = np.array([factor != dropped for factor in base_model.factors])
        weights = base_model.weights[keep]
        weights /= weights.sum()
        model = replace(
            base_model,
            factors=tuple(factor for factor in base_model.factors if factor != dropped),
            mean=base_model.mean[keep],
            scale=base_model.scale[keep],
            direction=base_model.direction[keep],
            weights=weights,
        )
        streams = _scaled_streams(
            _streams(development, model),
            int(definition["lookback"]),
            float(definition["target_volatility"]),
        )
        observations = [_observe(development, stream) for stream in streams]
        ablations.append(
            {
                "dropped_factor": dropped,
                "standard": observations[0],
                "cost_18bp": observations[1],
                "delay_5min_9bp": observations[2],
                "all_primary": all(v13._primary(item) for item in observations),
            }
        )

    neighborhood = []
    rejected = 0
    for decision, exit_bar, threshold, target, lookback in itertools.product(
        DECISIONS, EXITS, THRESHOLDS, TARGETS, LOOKBACKS
    ):
        model = _model(development, definition, decision, exit_bar, threshold)
        if model is None:
            rejected += 1
            continue
        streams = _scaled_streams(_streams(development, model), lookback, target)
        observations = [_observe(development, stream) for stream in streams]
        neighborhood.append(
            {
                "parameters": {
                    "decision": decision,
                    "exit": exit_bar,
                    "score_threshold": threshold,
                    "target_volatility": target,
                    "lookback": lookback,
                },
                "factors": model.factors,
                "standard": observations[0],
                "cost_18bp": observations[1],
                "delay_5min_9bp": observations[2],
                "all_primary": all(v13._primary(item) for item in observations),
            }
        )

    start_dates = {
        name: _start_date_metrics(development, stream)
        for name, stream in zip(("standard", "cost_18bp", "delay_5min_9bp"), base_streams)
    }
    start_date_passes = {
        start: all(
            float(start_dates[scenario][start]["annualized_return"]) > 0
            and float(start_dates[scenario][start]["max_drawdown"]) < 0.20
            for scenario in start_dates
        )
        for start in START_DATES
    }
    neighborhood_passes = sum(item["all_primary"] for item in neighborhood)
    ablation_primary_passes = sum(item["all_primary"] for item in ablations)
    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "candidate_id": args.candidate,
        "definition": definition,
        "selection_contract": "all focused stress parameters are fixed without 2026 ranking",
        "base": {
            "standard": _observe(development, base_streams[0]),
            "cost_18bp": _observe(development, base_streams[1]),
            "delay_5min_9bp": _observe(development, base_streams[2]),
        },
        "ablation": {
            "count": len(ablations),
            "all_primary_passes": ablation_primary_passes,
            "results": ablations,
        },
        "neighborhood": {
            "planned": len(DECISIONS)
            * len(EXITS)
            * len(THRESHOLDS)
            * len(TARGETS)
            * len(LOOKBACKS),
            "evaluated": len(neighborhood),
            "rejected": rejected,
            "all_primary_passes": neighborhood_passes,
            "pass_rate": neighborhood_passes / max(1, len(neighborhood)),
            "results": neighborhood,
        },
        "start_date_stress": {
            "results": start_dates,
            "positive_mdd_pass_by_start": start_date_passes,
            "passes": sum(start_date_passes.values()),
            "total": len(start_date_passes),
        },
        "multiple_comparison": {
            "global_bonferroni_5pct": False,
            "note": "candidate remains selected from a large correlated family; no multiplicity waiver",
        },
        "elapsed_seconds": time.perf_counter() - started,
    }
    v12._atomic(args.output, payload)
    print(
        json.dumps(
            {
                "candidate_id": args.candidate,
                "ablation_all_primary": f"{ablation_primary_passes}/{len(ablations)}",
                "neighborhood_all_primary": f"{neighborhood_passes}/{len(neighborhood)}",
                "start_date_passes": f"{sum(start_date_passes.values())}/{len(start_date_passes)}",
                "global_bonferroni_5pct": False,
                "elapsed_seconds": payload["elapsed_seconds"],
            }
        )
    )


if __name__ == "__main__":
    main()
