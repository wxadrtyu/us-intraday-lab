"""Second hundred-round campaign using multi-horizon factor events and cash states."""

from __future__ import annotations

import argparse
import itertools
import json
import math
import time
from pathlib import Path

import analyze_full_universe_intraday_v53_cross_asset_factors as v53
import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v42_multifactor_vol_target as v42
import evaluate_full_universe_intraday_v47_score_slope as v47
import evaluate_full_universe_intraday_v57_hundred_round_multifactor as v57
import numpy as np
import search_full_universe_intraday_v12_robustness as v12
import search_full_universe_intraday_v13_regime_rotation as v13

from us_intraday_lab.fast_intraday_research import metrics

SCHEDULES = (
    ((8, 11, 14, 17), 47),
    ((17, 20, 23, 26), 65),
    ((20, 23, 26, 29), 72),
    ((29, 32, 35, 38), 69),
    ((35, 38, 41, 44), 75),
)
WEIGHTINGS = ("equal", "reliability")
THRESHOLDS = (0.25, 0.50, 0.75, 1.0)
CONFIRMATIONS = (1, 2)
TARGETS = (0.30, 0.35)
LOOKBACKS = (15, 20)
TOP_PER_ROUND = 5


def _scores(cube: v53.Cube, models: list[v57.Model], weighting: str):
    output = []
    for model in models:
        specification = {
            "decision": model.decision,
            "exit": model.exit_bar,
            "assets": v57.ASSETS,
        }
        matrix, _, _ = v34._matrix(cube, specification, model.factors)
        weights = model.reliability.copy()
        if weighting == "equal":
            weights[:] = 1.0
        weights /= weights.sum()
        score = np.einsum(
            "saf,f,f->sa",
            (matrix - model.mean) / model.scale,
            model.direction,
            weights,
        )
        output.append(np.where(np.isfinite(matrix).all(axis=2), score, -np.inf))
    return output


def _trigger(
    scores: list[np.ndarray], horizons: tuple[int, ...], threshold: float, confirmations: int
):
    selected = np.full(len(scores[0]), -1, dtype=int)
    decision = np.full(len(scores[0]), -1, dtype=int)
    previous_asset = np.full(len(scores[0]), -1, dtype=int)
    previous_above = np.zeros(len(scores[0]), dtype=bool)
    rows = np.arange(len(scores[0]))
    for score, horizon in zip(scores, horizons, strict=True):
        local = np.argmax(score, axis=1)
        asset = v57.ASSETS[local]
        best = score[rows, local]
        above = np.isfinite(best) & (best >= threshold)
        event = (selected < 0) & above
        if confirmations == 2:
            event &= previous_above & (previous_asset == asset)
        selected[event] = asset[event]
        decision[event] = horizon
        previous_asset = asset
        previous_above = above
    return selected, decision


def _raw(
    cube: v53.Cube,
    selected: np.ndarray,
    decision: np.ndarray,
    exit_bar: int,
    cost: float,
    delay: int,
):
    safe_asset = np.maximum(selected, 0)
    entry = decision + 1 + delay
    safe_entry = np.maximum(entry, 0)
    active = (selected >= 0) & (entry < exit_bar)
    active &= (
        cube.first[cube.rows, safe_entry, safe_asset] <= safe_entry * 5 + cube.boundary_tolerance
    )
    active &= cube.first[cube.rows, exit_bar, safe_asset] <= exit_bar * 5 + cube.boundary_tolerance
    active &= np.isfinite(cube.opens[cube.rows, safe_entry, safe_asset])
    active &= np.isfinite(cube.opens[cube.rows, exit_bar, safe_asset])
    active &= np.isfinite(cube.opens[cube.rows, safe_entry, 0])
    active &= np.isfinite(cube.opens[:, exit_bar, 0])
    active &= cube.opens[cube.rows, safe_entry, safe_asset] > 0
    active &= cube.opens[cube.rows, safe_entry, 0] > 0
    values = np.zeros(len(cube.sessions))
    values[active] = (
        cube.opens[active, exit_bar, safe_asset[active]]
        / cube.opens[cube.rows[active], safe_entry[active], safe_asset[active]]
        - 1.0
        - cost
    )
    benchmark = np.zeros(len(cube.sessions))
    benchmark[active] = (
        cube.opens[active, exit_bar, 0] / cube.opens[cube.rows[active], safe_entry[active], 0] - 1.0
    )
    return v12.ReturnStream(values, benchmark, active, active.astype(int))


def _scaled(raw: tuple[v12.ReturnStream, ...], target: float, lookback: int):
    exposure = v42._exposure(raw[0].values, lookback, target, 0.0)
    return tuple(v42._scaled(stream, exposure) for stream in raw)


def _definition(
    round_id: int, template: str, horizons: tuple[int, ...], exit_bar: int, values: tuple
):
    weighting, threshold, confirmations, target, lookback = values
    return {
        "round": round_id,
        "template": template,
        "factors": v57.TEMPLATES[template],
        "horizons": horizons,
        "exit": exit_bar,
        "weighting": weighting,
        "score_threshold": threshold,
        "confirmations": confirmations,
        "target_volatility": target,
        "lookback": lookback,
    }


def _neighbor_share(definition: dict, cells: list[dict]) -> float:
    varying = ("weighting", "score_threshold", "confirmations", "target_volatility", "lookback")
    neighbors = [
        item
        for item in cells
        if sum(item["definition"][name] != definition[name] for name in varying) == 1
    ]
    if not neighbors:
        return 0.0
    return sum(
        float(item["observations"][0]["development_oos_2024_2025"]["annualized_return"]) > 0
        for item in neighbors
    ) / len(neighbors)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if len(v57.TEMPLATES) != 20 or len(SCHEDULES) != 5:
        raise RuntimeError("v58 contract requires exactly 100 event-ensemble rounds")
    started = time.perf_counter()
    development = v53.Cube(args.root, "alpaca", 0)
    historical = v53.Cube(args.root, "historical", 0)
    planned = (
        len(v57.TEMPLATES)
        * len(SCHEDULES)
        * len(WEIGHTINGS)
        * len(THRESHOLDS)
        * len(CONFIRMATIONS)
        * len(TARGETS)
        * len(LOOKBACKS)
    )
    rounds = []
    frontier = []
    round_id = 0
    for template, factors in v57.TEMPLATES.items():
        for horizons, exit_bar in SCHEDULES:
            round_id += 1
            models = [v57._fit(development, factors, decision, exit_bar) for decision in horizons]
            if any(model is None for model in models):
                rounds.append({"round": round_id, "template": template, "status": "FIT_REJECTED"})
                continue
            frozen_models = [model for model in models if model is not None]
            score_cache = {
                weighting: _scores(development, frozen_models, weighting)
                for weighting in WEIGHTINGS
            }
            raw_cache = {}
            cells = []
            for weighting, threshold, confirmations in itertools.product(
                WEIGHTINGS, THRESHOLDS, CONFIRMATIONS
            ):
                selected, decision = _trigger(
                    score_cache[weighting], horizons, threshold, confirmations
                )
                raw_cache[(weighting, threshold, confirmations)] = (
                    _raw(development, selected, decision, exit_bar, v34.STANDARD_COST, 0),
                    _raw(development, selected, decision, exit_bar, v34.STRESS_COST, 0),
                    _raw(development, selected, decision, exit_bar, v34.STANDARD_COST, 1),
                )
            for values in itertools.product(
                WEIGHTINGS, THRESHOLDS, CONFIRMATIONS, TARGETS, LOOKBACKS
            ):
                weighting, threshold, confirmations, target, lookback = values
                definition = _definition(round_id, template, horizons, exit_bar, values)
                streams = _scaled(
                    raw_cache[(weighting, threshold, confirmations)], target, lookback
                )
                observations = [v47._observe(development, stream) for stream in streams]
                cells.append(
                    {
                        "definition": definition,
                        "models": frozen_models,
                        "streams": streams,
                        "observations": observations,
                        "rank": v47._rank(*observations),
                    }
                )
            cells.sort(key=lambda item: item["rank"], reverse=True)
            rounds.append(
                {
                    "round": round_id,
                    "template": template,
                    "horizons": horizons,
                    "exit": exit_bar,
                    "status": "COMPLETE",
                    "evaluated_cells": len(cells),
                    "best_rank": list(cells[0]["rank"]),
                }
            )
            for item in cells[:TOP_PER_ROUND]:
                item["neighbor_positive_share"] = _neighbor_share(item["definition"], cells)
                frontier.append(item)
    frontier.sort(key=lambda item: item["rank"], reverse=True)
    folds = np.array_split(np.flatnonzero(development.masks()["development_all"]), 5)
    historical_cache = {}
    records = []
    pre_null_hits = 0
    for item in frontier:
        definition = item["definition"]
        key = (
            int(definition["round"]),
            definition["weighting"],
            float(definition["score_threshold"]),
            int(definition["confirmations"]),
        )
        if key not in historical_cache:
            scores = _scores(historical, item["models"], str(definition["weighting"]))
            selected, decision = _trigger(
                scores,
                tuple(int(value) for value in definition["horizons"]),
                float(definition["score_threshold"]),
                int(definition["confirmations"]),
            )
            historical_cache[key] = _raw(
                historical, selected, decision, int(definition["exit"]), v34.STANDARD_COST, 0
            )
        historical_stream = _scaled(
            (historical_cache[key],),
            float(definition["target_volatility"]),
            int(definition["lookback"]),
        )[0]
        streams = item["streams"]
        standard, cost, delay = [v47._observe(development, stream, True) for stream in streams]
        historical_obs = v47._observe(historical, historical_stream, True)["historical_2018_2020"]
        fold_obs = [
            metrics(streams[0].values[index], streams[0].benchmark[index], streams[0].active[index])
            for index in folds
        ]
        oos = standard["development_oos_2024_2025"]
        consumed = standard["consumed_2026_all"]
        z_score = float(oos["information_ratio"]) * math.sqrt(max(1, int(oos["trades"])) / 252)
        gates = {
            "standard_primary": v13._primary(standard),
            "cost_18bp_primary": v13._primary(cost),
            "delay_5min_primary": v13._primary(delay),
            "four_of_five_positive_folds": sum(float(x["annualized_return"]) > 0 for x in fold_obs)
            >= 4,
            "historical_positive_mdd_below_20pct": float(historical_obs["annualized_return"]) > 0
            and float(historical_obs["max_drawdown"]) < 0.20,
            "parameter_neighborhood_75pct_positive": float(item["neighbor_positive_share"]) >= 0.75,
            "global_bonferroni_5pct": min(
                1.0, 2.0 * v47._normal_tail(abs(z_score)) * max(1, planned)
            )
            < 0.05,
            "consumed_2026_total_above_5pct": float(consumed["total_return"]) > 0.05,
        }
        core = (
            "standard_primary",
            "cost_18bp_primary",
            "delay_5min_primary",
            "four_of_five_positive_folds",
            "historical_positive_mdd_below_20pct",
            "parameter_neighborhood_75pct_positive",
            "consumed_2026_total_above_5pct",
        )
        pre_null_hits += int(all(gates[name] for name in core))
        records.append(
            {
                "candidate_id": v12._identity(definition, "lev-v58e-"),
                "definition": definition,
                "models": [
                    {
                        "decision": model.decision,
                        "mean": model.mean.tolist(),
                        "scale": model.scale.tolist(),
                        "direction": model.direction.tolist(),
                        "reliability": model.reliability.tolist(),
                    }
                    for model in item["models"]
                ],
                "development_rank": list(item["rank"]),
                "standard": standard,
                "cost_18bp": cost,
                "delay_5min_9bp": delay,
                "historical_2018_2020": historical_obs,
                "folds": fold_obs,
                "neighbor_positive_share": item["neighbor_positive_share"],
                "gates": gates,
            }
        )
    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "selection_contract": (
            "second exact 100-round batch uses train-only factor directions and multi-horizon "
            "event confirmation; 2026 is attached only after each round freezes five candidates"
        ),
        "revised_2026_gate": {
            "metric": "consumed_2026_all.total_return",
            "operator": ">",
            "threshold": 0.05,
        },
        "scan": {
            "planned_rounds": 100,
            "evaluated_rounds": len(rounds),
            "planned_cells": planned,
            "evaluated_cells": sum(int(x.get("evaluated_cells", 0)) for x in rounds),
            "frozen_frontier": len(frontier),
            "elapsed_seconds": time.perf_counter() - started,
        },
        "pre_factory_null_hits": pre_null_hits,
        "rounds": rounds,
        "records": records,
    }
    v12._atomic(args.output, payload)
    print(json.dumps({"scan": payload["scan"], "pre_factory_null_hits": pre_null_hits}))
    if records:
        best = records[0]
        print(
            json.dumps(
                {
                    "candidate_id": best["candidate_id"],
                    "definition": best["definition"],
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
