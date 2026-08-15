"""Causal portfolio-state gates for the frozen v38 multi-factor frontier."""

from __future__ import annotations

import argparse
import itertools
import json
import math
import time
from pathlib import Path

import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v35_rank_ensemble as v35
import evaluate_full_universe_intraday_v38_multifactor_sleeve_beam as v38
import numpy as np
import search_full_universe_intraday_v12_robustness as v12
import search_full_universe_intraday_v13_regime_rotation as v13
import search_full_universe_intraday_v15_prior5 as v15

from us_intraday_lab.fast_intraday_research import metrics

PRIOR20_FLOORS = (-0.10, -0.05, 0.0, 0.05)
CURRENT_FLOORS = (-0.02, -0.01, 0.0, 0.005)
BREADTH_FLOORS = (0.25, 0.40, 0.50, 0.60)
VOLATILITY_QUANTILES = (0.50, 0.70, 0.90, 1.0)


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


def _filtered(stream: v12.ReturnStream, gate: np.ndarray) -> v12.ReturnStream:
    active = stream.active & gate
    return v12.ReturnStream(
        np.where(gate, stream.values, 0.0),
        np.where(gate, stream.benchmark, 0.0),
        active,
        np.where(gate, stream.component_trades, 0),
    )


def _models(cube: v34.Cube, definitions: list[dict]):
    models = []
    for definition in definitions:
        if "assets" in definition:
            specification = {
                "name": "daily_once",
                "decision": definition["decision"],
                "exit": definition["exit"],
                "assets": tuple(definition["assets"]),
            }
        else:
            specification = {
                "name": definition["slot"],
                "decision": definition["decision"],
                "exit": definition["exit"],
                "assets": v38.ASSET_PROFILES[definition["profile"]][definition["slot"]],
            }
        matrix, finite, diagnostics = v38._diagnostics(cube, specification)
        model = v38._model(
            cube,
            specification,
            matrix,
            finite,
            diagnostics,
            float(definition["ic_floor"]),
            str(definition["selection_mode"]),
            str(definition["weighting"]),
            float(definition["score_threshold"]),
        )
        if model is None:
            raise RuntimeError("frozen v38 sleeve no longer fits")
        models.append(model)
    return models


def _streams(cube: v34.Cube, models: list[v35.RankModel]):
    return (
        v13._combine([v35._sleeve(cube, model, v34.STANDARD_COST, 0) for model in models]),
        v13._combine([v35._sleeve(cube, model, v34.STRESS_COST, 0) for model in models]),
        v13._combine([v35._sleeve(cube, model, v34.STANDARD_COST, 1) for model in models]),
    )


def _state(cube: v34.Cube, decision: int):
    factors = cube.factors(decision)
    return {
        "prior20": cube.prior20[:, 0],
        "current": factors["current_return"][:, 0],
        "breadth": factors["sector_breadth"][:, 0],
        "volatility": factors["realized_volatility"][:, 0],
    }


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
    parser.add_argument("--parents", default=100, type=int)
    parser.add_argument("--frontier", default=500, type=int)
    args = parser.parse_args()
    started = time.perf_counter()
    source = json.loads(args.source.read_text(encoding="utf-8"))
    parents = source["records"][: args.parents]
    development = v34.Cube(args.root, "alpaca", 0)
    train = development.masks()["train_2022_2023"]
    frontier = []
    scanned = 0
    development_models = {}
    for parent in parents:
        sleeves = parent.get("sleeves", [parent["definition"]])
        models = _models(development, sleeves)
        development_models[parent["candidate_id"]] = models
        streams = _streams(development, models)
        decision = min(int(item["decision"]) for item in sleeves)
        state = _state(development, decision)
        train_volatility = state["volatility"][train & np.isfinite(state["volatility"])]
        for prior20, current, breadth, vol_quantile in itertools.product(
            PRIOR20_FLOORS, CURRENT_FLOORS, BREADTH_FLOORS, VOLATILITY_QUANTILES
        ):
            scanned += 1
            vol_ceiling = float(np.quantile(train_volatility, vol_quantile))
            gate = (
                np.isfinite(state["prior20"])
                & np.isfinite(state["current"])
                & np.isfinite(state["breadth"])
                & np.isfinite(state["volatility"])
                & (state["prior20"] >= prior20)
                & (state["current"] >= current)
                & (state["breadth"] >= breadth)
                & (state["volatility"] <= vol_ceiling)
            )
            standard_stream, cost_stream, delay_stream = (
                _filtered(stream, gate) for stream in streams
            )
            standard = _observe(development, standard_stream)
            cost = _observe(development, cost_stream)
            delay = _observe(development, delay_stream)
            definition = {
                "parent_id": parent["candidate_id"],
                "sleeves": sleeves,
                "gate_decision": decision,
                "prior20_floor": prior20,
                "current_floor": current,
                "breadth_floor": breadth,
                "volatility_quantile": vol_quantile,
                "volatility_ceiling": vol_ceiling,
            }
            frontier.append(
                (
                    _rank(standard, cost, delay),
                    v12._identity(definition, "lev-v39g-"),
                    definition,
                )
            )
    frontier.sort(key=lambda item: item[0], reverse=True)
    frontier = frontier[: args.frontier]

    # Development ranking is frozen before either older history or 2026 is observed.
    historical = v34.Cube(args.root, "historical", 0)
    folds = np.array_split(np.flatnonzero(development.masks()["development_all"]), 5)
    records = []
    eligible = 0
    diagnostic_hits = 0
    for rank, candidate_id, definition in frontier:
        models = development_models[definition["parent_id"]]
        development_streams = _streams(development, models)
        state = _state(development, int(definition["gate_decision"]))
        gate = (
            np.isfinite(state["prior20"])
            & np.isfinite(state["current"])
            & np.isfinite(state["breadth"])
            & np.isfinite(state["volatility"])
            & (state["prior20"] >= float(definition["prior20_floor"]))
            & (state["current"] >= float(definition["current_floor"]))
            & (state["breadth"] >= float(definition["breadth_floor"]))
            & (state["volatility"] <= float(definition["volatility_ceiling"]))
        )
        filtered = [_filtered(stream, gate) for stream in development_streams]
        standard, cost, delay = [_observe(development, stream, True) for stream in filtered]
        historical_stream = _streams(historical, models)[0]
        historical_state = _state(historical, int(definition["gate_decision"]))
        historical_gate = (
            np.isfinite(historical_state["prior20"])
            & np.isfinite(historical_state["current"])
            & np.isfinite(historical_state["breadth"])
            & np.isfinite(historical_state["volatility"])
            & (historical_state["prior20"] >= float(definition["prior20_floor"]))
            & (historical_state["current"] >= float(definition["current_floor"]))
            & (historical_state["breadth"] >= float(definition["breadth_floor"]))
            & (historical_state["volatility"] <= float(definition["volatility_ceiling"]))
        )
        historical_obs = _observe(historical, _filtered(historical_stream, historical_gate), True)[
            "historical_2018_2020"
        ]
        fold_obs = [
            metrics(stream.values[index], stream.benchmark[index], stream.active[index])
            for index in folds
            for stream in filtered[:1]
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
        "selection_contract": "portfolio state gates ranked on 2022-2025 only",
        "factor_version": v34.FACTOR_VERSION,
        "scan": {
            "parents": len(parents),
            "gate_trials": scanned,
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
