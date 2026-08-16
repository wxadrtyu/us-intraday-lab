"""Low-frequency oversold reversal after cross-sector breadth stabilization."""

from __future__ import annotations

import argparse
import itertools
import json
import math
import time
from pathlib import Path

import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v42_multifactor_vol_target as v42
import evaluate_full_universe_intraday_v47_score_slope as v47
import numpy as np
import search_full_universe_intraday_v12_robustness as v12
import search_full_universe_intraday_v13_regime_rotation as v13

from us_intraday_lab.fast_intraday_research import metrics

DECISIONS = (35, 41, 47)
EXITS = (69, 72, 75)
ASSETS = np.array((3, 4))
DRAWDOWN_CEILINGS = (-0.01, -0.02, -0.03)
BOUNCE_FLOORS = (0.0, 0.0025, 0.005)
BREADTH_DELTA_FLOORS = (0.0, 0.10)
VOLUME_ACCELERATION_CEILINGS = (0.0, 0.25)
PRIOR20_FLOORS = (-0.20, -0.10)
TARGETS = (0.25, 0.30, 0.35)
LOOKBACKS = (15, 20)
WEAK_MARKET_2026_MIN_TOTAL_RETURN = 0.05


def _selection(cube: v34.Cube, definition: dict):
    decision = int(definition["decision"])
    earlier = decision - 6
    factors = cube.factors(decision)
    earlier_factors = cube.factors(earlier)
    current = factors["current_return"][:, ASSETS]
    recent = factors["recent_return"][:, ASSETS]
    volume = factors["volume_acceleration"][:, ASSETS]
    prior20 = factors["prior20_return"][:, ASSETS]
    breadth = factors["sector_breadth"][:, ASSETS]
    earlier_breadth = earlier_factors["sector_breadth"][:, ASSETS]
    breadth_delta = breadth - earlier_breadth
    finite = (
        np.isfinite(current)
        & np.isfinite(recent)
        & np.isfinite(volume)
        & np.isfinite(prior20)
        & np.isfinite(breadth_delta)
    )
    eligible = (
        finite
        & (current <= float(definition["drawdown_ceiling"]))
        & (recent >= float(definition["bounce_floor"]))
        & (breadth_delta >= float(definition["breadth_delta_floor"]))
        & (volume <= float(definition["volume_acceleration_ceiling"]))
        & (prior20 >= float(definition["prior20_floor"]))
    )
    score = -current + 2.0 * recent + 0.10 * breadth_delta
    score = np.where(eligible, score, -np.inf)
    local = np.argmax(score, axis=1)
    best = score[cube.rows, local]
    selected = ASSETS[local]
    return selected, np.isfinite(best)


def _stream(cube: v34.Cube, definition: dict, cost: float, delay: int):
    selected, active = _selection(cube, definition)
    decision = int(definition["decision"])
    exit_bar = int(definition["exit"])
    entry = decision + 1 + delay
    active &= entry < exit_bar
    active &= cube.first[cube.rows, entry, selected] <= entry * 5 + cube.boundary_tolerance
    active &= cube.first[cube.rows, exit_bar, selected] <= exit_bar * 5 + cube.boundary_tolerance
    active &= np.isfinite(cube.opens[cube.rows, entry, selected])
    active &= np.isfinite(cube.opens[cube.rows, exit_bar, selected])
    active &= np.isfinite(cube.opens[:, entry, 0])
    active &= np.isfinite(cube.opens[:, exit_bar, 0])
    active &= cube.opens[cube.rows, entry, selected] > 0
    active &= cube.opens[:, entry, 0] > 0
    values = np.zeros(len(cube.sessions))
    values[active] = (
        cube.opens[active, exit_bar, selected[active]] / cube.opens[active, entry, selected[active]]
        - 1.0
        - cost
    )
    benchmark = np.zeros(len(cube.sessions))
    benchmark[active] = cube.opens[active, exit_bar, 0] / cube.opens[active, entry, 0] - 1.0
    return v12.ReturnStream(values, benchmark, active, active.astype(int))


def _scaled(cube: v34.Cube, definition: dict):
    raw = (
        _stream(cube, definition, v34.STANDARD_COST, 0),
        _stream(cube, definition, v34.STRESS_COST, 0),
        _stream(cube, definition, v34.STANDARD_COST, 1),
    )
    exposure = v42._exposure(
        raw[0].values,
        int(definition["lookback"]),
        float(definition["target_volatility"]),
        0.0,
    )
    return tuple(v42._scaled(stream, exposure) for stream in raw)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    development = v34.Cube(args.root, "alpaca", 0)
    candidates = []
    planned = 0
    grid = itertools.product(
        DECISIONS,
        EXITS,
        DRAWDOWN_CEILINGS,
        BOUNCE_FLOORS,
        BREADTH_DELTA_FLOORS,
        VOLUME_ACCELERATION_CEILINGS,
        PRIOR20_FLOORS,
        TARGETS,
        LOOKBACKS,
    )
    for decision, exit_bar, drawdown, bounce, breadth, volume, prior20, target, lookback in grid:
        planned += 1
        definition = {
            "decision": decision,
            "exit": exit_bar,
            "assets": ASSETS.tolist(),
            "drawdown_ceiling": drawdown,
            "bounce_floor": bounce,
            "breadth_delta_floor": breadth,
            "volume_acceleration_ceiling": volume,
            "prior20_floor": prior20,
            "target_volatility": target,
            "lookback": lookback,
            "factors": (
                "current_return",
                "recent_return",
                "sector_breadth_delta_30min",
                "volume_acceleration",
                "prior20_return",
            ),
        }
        streams = _scaled(development, definition)
        observations = [v47._observe(development, stream) for stream in streams]
        candidates.append(
            (
                v47._rank(*observations),
                v12._identity(definition, "lev-v56b-"),
                definition,
                streams,
            )
        )
    candidates.sort(key=lambda item: item[0], reverse=True)

    historical = v34.Cube(args.root, "historical", 0)
    folds = np.array_split(np.flatnonzero(development.masks()["development_all"]), 5)
    records = []
    revised_gate_hits = 0
    for rank, candidate_id, definition, streams in candidates:
        standard, cost, delay = [v47._observe(development, stream, True) for stream in streams]
        historical_obs = v47._observe(historical, _scaled(historical, definition)[0], True)[
            "historical_2018_2020"
        ]
        fold_obs = [
            metrics(streams[0].values[index], streams[0].benchmark[index], streams[0].active[index])
            for index in folds
        ]
        consumed = standard["consumed_2026_all"]
        oos = standard["development_oos_2024_2025"]
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
                1.0, 2.0 * v47._normal_tail(abs(z_score)) * max(1, planned)
            )
            < 0.05,
            "consumed_2026_total_above_5pct": float(consumed["total_return"])
            > WEAK_MARKET_2026_MIN_TOTAL_RETURN,
        }
        revised_gate_hits += int(
            all(
                gates[name]
                for name in (
                    "standard_primary",
                    "cost_18bp_primary",
                    "delay_5min_primary",
                    "four_of_five_positive_folds",
                    "historical_positive_mdd_below_20pct",
                    "consumed_2026_total_above_5pct",
                )
            )
        )
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
        "selection_contract": (
            "five-factor breadth-stabilization reversal frozen on 2022-2025 before historical "
            "and consumed-2026 diagnostics"
        ),
        "revised_2026_gate": {
            "metric": "consumed_2026_all.total_return",
            "operator": ">",
            "threshold": WEAK_MARKET_2026_MIN_TOTAL_RETURN,
        },
        "scan": {
            "planned_trials": planned,
            "evaluated_trials": len(candidates),
            "elapsed_seconds": time.perf_counter() - started,
        },
        "revised_gate_hits_before_factory_null": revised_gate_hits,
        "records": records,
    }
    v12._atomic(args.output, payload)
    print(
        json.dumps(
            {
                "scan": payload["scan"],
                "revised_gate_hits_before_factory_null": revised_gate_hits,
            }
        )
    )
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
