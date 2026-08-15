"""Diversified sleeve retention followed by development-only portfolio beams."""

from __future__ import annotations

import argparse
import heapq
import itertools
import json
import math
import time
from pathlib import Path
from typing import Any

import numpy as np
import search_full_universe_intraday_v12_robustness as v12
import search_full_universe_intraday_v13_regime_rotation as v13
import search_full_universe_intraday_v15_prior5 as v15

from us_intraday_lab.fast_intraday_research import metrics

DEVELOPMENT_NAMES = v15.DEVELOPMENT_NAMES
SLOTS = {
    "opening": ((2, 5, 8), (12, 15, 18, 23)),
    "morning": ((17, 23, 29), (36, 42, 47)),
    "midday": ((41, 44, 47, 50), (53, 56)),
    "afternoon": ((47, 53, 59), (66, 72, 77)),
    "late": ((68, 71, 74), (77,)),
}


def _observe(cube: v15.Cube, stream: v12.ReturnStream) -> dict[str, Any]:
    masks = cube.masks()
    names = DEVELOPMENT_NAMES + ("development_oos_2024_2025",)
    return {
        name: metrics(
            stream.values[masks[name]], stream.benchmark[masks[name]], stream.active[masks[name]]
        )
        for name in names
    }


def _criterion(observations: dict[str, Any], name: str) -> tuple[float, float]:
    item = observations[name]
    return float(item["annualized_return"]), float(item["information_ratio"])


def _shortlist(
    cube: v15.Cube, slot: str, per_group: int, global_per_criterion: int
) -> tuple[list[v13.Sleeve], int]:
    heaps: dict[tuple[str, str], list[tuple[tuple[float, float], int, v13.Sleeve]]] = {}
    scanned = 0
    serial = 0
    for specification in v15._specifications(slot):
        scanned += 1
        standard = cube.replay_spec(specification)
        observations = _observe(cube, standard)
        if any(
            int(observations[name]["trades"]) < minimum
            for name, minimum in zip(DEVELOPMENT_NAMES, (10, 3, 3), strict=True)
        ):
            continue
        p = specification["parameters"]
        group = f"{specification['family']}:{p['decision']}:{p['exit']}:{p['universe']}"
        rank = (
            min(float(observations[name]["annualized_return"]) for name in DEVELOPMENT_NAMES),
            float(observations["development_oos_2024_2025"]["annualized_return"]),
            float(observations["development_oos_2024_2025"]["information_ratio"]),
        )
        sleeve = v13.Sleeve(specification, standard, None, None, observations, rank)
        for criterion in DEVELOPMENT_NAMES + ("development_oos_2024_2025",):
            item = (_criterion(observations, criterion), serial, sleeve)
            serial += 1
            heap = heaps.setdefault((group, criterion), [])
            if len(heap) < per_group:
                heapq.heappush(heap, item)
            elif item[:2] > heap[0][:2]:
                heapq.heapreplace(heap, item)
    grouped = {
        v12._identity(item[2].specification, "lev-v18s-"): item[2]
        for heap in heaps.values()
        for item in heap
    }
    selected: dict[str, v13.Sleeve] = {}
    for criterion in DEVELOPMENT_NAMES + ("development_oos_2024_2025",):
        ordered = sorted(
            grouped.values(),
            key=lambda sleeve: _criterion(sleeve.observations, criterion),
            reverse=True,
        )
        for sleeve in ordered[:global_per_criterion]:
            selected[v12._identity(sleeve.specification, "lev-v18s-")] = sleeve
    output = list(selected.values())
    for sleeve in output:
        sleeve.cost_18bp = cube.replay_spec(sleeve.specification, 0.0018)
        sleeve.delay_5m = cube.replay_spec(sleeve.specification, 0.0009, 1)
    return output, scanned


def _portfolio_rank(cube: v15.Cube, sleeves: tuple[v13.Sleeve, ...]) -> tuple[float, float, float]:
    standard = _observe(cube, v13._combine([item.standard for item in sleeves]))
    cost = _observe(
        cube,
        v13._combine([item.cost_18bp for item in sleeves if item.cost_18bp is not None]),
    )
    delay = _observe(
        cube,
        v13._combine([item.delay_5m for item in sleeves if item.delay_5m is not None]),
    )
    return (
        min(float(standard[name]["annualized_return"]) for name in DEVELOPMENT_NAMES),
        min(
            float(cost["development_oos_2024_2025"]["annualized_return"]),
            float(delay["development_oos_2024_2025"]["annualized_return"]),
        ),
        min(
            float(cost["development_oos_2024_2025"]["information_ratio"]),
            float(delay["development_oos_2024_2025"]["information_ratio"]),
        ),
    )


def _beam(
    cube: v15.Cube,
    shortlisted: dict[str, list[v13.Sleeve]],
    keep: int,
    max_sleeves: int,
) -> tuple[list[dict[str, Any]], int]:
    beam: list[tuple[tuple[float, float, float], int, tuple[v13.Sleeve, ...]]] = []
    serial = 0
    scanned = 0
    for slot in SLOTS:
        prefixes = [item[2] for item in beam] if beam else [()]
        expanded = []
        for prefix in prefixes:
            for option in [None, *shortlisted[slot]]:
                sleeves = prefix if option is None else prefix + (option,)
                if not sleeves or len(sleeves) > max_sleeves:
                    continue
                boundaries = [
                    (
                        int(item.specification["parameters"]["decision"]) + 1,
                        int(item.specification["parameters"]["exit"]),
                    )
                    for item in sleeves
                ]
                if any(left[1] >= right[0] for left, right in itertools.pairwise(boundaries)):
                    continue
                scanned += 1
                expanded.append((_portfolio_rank(cube, sleeves), serial, sleeves))
                serial += 1
        expanded.sort(key=lambda item: (item[0], item[1]), reverse=True)
        unique = {}
        for item in expanded:
            identity = v12._identity([sleeve.specification for sleeve in item[2]], "lev-v18p-")
            unique.setdefault(identity, item)
            if len(unique) >= keep:
                break
        beam = list(unique.values())
    return (
        [
            {
                "candidate_id": v12._identity(
                    [item.specification for item in sleeves], "lev-v18p-"
                ),
                "specifications": [item.specification for item in sleeves],
                "development_rank": list(rank),
            }
            for rank, _, sleeves in beam
        ],
        scanned,
    )


def _normal_tail(value: float) -> float:
    return 0.5 * math.erfc(value / math.sqrt(2.0))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--per-group", default=2, type=int)
    parser.add_argument("--global-per-criterion", default=20, type=int)
    parser.add_argument("--beam-width", default=5000, type=int)
    parser.add_argument("--max-sleeves", default=5, type=int)
    args = parser.parse_args()
    started = time.perf_counter()
    v15.SLOTS = SLOTS
    development = v15.Cube(args.root, "alpaca", 0)
    shortlisted: dict[str, list[v13.Sleeve]] = {}
    sleeve_cells = {}
    for slot in SLOTS:
        shortlisted[slot], sleeve_cells[slot] = _shortlist(
            development, slot, args.per_group, args.global_per_criterion
        )
    frontier, portfolio_cells = _beam(development, shortlisted, args.beam_width, args.max_sleeves)

    # The beam is frozen before this consumed/historical block begins.
    historical = v15.Cube(args.root, "historical", 0)
    masks = development.masks()
    folds = np.array_split(np.flatnonzero(masks["development_all"]), 5)
    total_trials = sum(sleeve_cells.values()) + portfolio_cells
    eligible = 0
    diagnostic_hits = 0
    for record in frontier:
        specs = record["specifications"]
        standard_stream = v13._combine([development.replay_spec(spec) for spec in specs])
        standard = v13._observe(development, standard_stream)
        cost = v13._observe(
            development,
            v13._combine([development.replay_spec(spec, 0.0018) for spec in specs]),
        )
        delay = v13._observe(
            development,
            v13._combine([development.replay_spec(spec, 0.0009, 1) for spec in specs]),
        )
        historical_observation = v13._observe(
            historical, v13._combine([historical.replay_spec(spec) for spec in specs])
        )
        fold_observations = [
            metrics(
                standard_stream.values[index],
                standard_stream.benchmark[index],
                standard_stream.active[index],
            )
            for index in folds
        ]
        oos = standard["development_oos_2024_2025"]
        consumed = standard["consumed_2026_all"]
        hist = historical_observation["historical_2018_2020"]
        z_score = float(oos["information_ratio"]) * math.sqrt(max(1, int(oos["trades"])) / 252)
        bonferroni = min(1.0, 2.0 * _normal_tail(abs(z_score)) * total_trials)
        gates = {
            "standard_primary": v15._primary(standard),
            "cost_18bp_primary": v15._primary(cost),
            "delay_5min_primary": v15._primary(delay),
            "four_of_five_positive_folds": sum(
                float(item["annualized_return"]) > 0 for item in fold_observations
            )
            >= 4,
            "historical_positive_mdd_below_20pct": float(hist["annualized_return"]) > 0
            and float(hist["max_drawdown"]) < 0.20,
            "consumed_2026_total_above_20pct": float(consumed["total_return"]) > 0.20,
            "consumed_2026_mdd_below_20pct": float(consumed["max_drawdown"]) < 0.20,
            "consumed_2026_ir_at_least_1": float(consumed["information_ratio"]) >= 1.0,
            "multiple_comparison_bonferroni_5pct": bonferroni < 0.05,
            "start_date_stress_evaluated": False,
            "parameter_neighborhood_evaluated": False,
        }
        record.update(
            {
                "standard": standard,
                "cost_18bp": cost,
                "delay_5min_9bp": delay,
                "historical_cross_source": historical_observation,
                "development_folds": fold_observations,
                "multiple_comparison": {"total_trials": total_trials, "bonferroni_p": bonferroni},
                "gates": gates,
                "eligible_for_future_simulation_observation": all(gates.values()),
            }
        )
        diagnostic_hits += int(gates["consumed_2026_total_above_20pct"])
        eligible += int(record["eligible_for_future_simulation_observation"])
    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "selection_contract": "diversified sleeve and portfolio retention use 2022-2025 only",
        "execution_contract": "long-only; gross<=1; no overnight; exact boundaries; <=5 non-overlapping sparse sleeves",
        "scan": {
            "sleeve_cells": sleeve_cells,
            "shortlisted": {key: len(value) for key, value in shortlisted.items()},
            "portfolio_cells": portfolio_cells,
            "total_trials": total_trials,
            "frontier_size": len(frontier),
            "elapsed_seconds": time.perf_counter() - started,
        },
        "diagnostic_2026_above_20_count": diagnostic_hits,
        "eligible_count": eligible,
        "frontier": frontier,
    }
    v12._atomic(args.output, payload)
    print(
        json.dumps(
            {"scan": payload["scan"], "diagnostic_hits": diagnostic_hits, "eligible": eligible}
        )
    )
    if frontier:
        best = max(
            frontier, key=lambda item: float(item["standard"]["consumed_2026_all"]["total_return"])
        )
        print(
            json.dumps(
                {
                    "candidate_id": best["candidate_id"],
                    "development_rank": best["development_rank"],
                    "oos": best["standard"]["development_oos_2024_2025"],
                    "consumed_2026": best["standard"]["consumed_2026_all"],
                    "gates": best["gates"],
                },
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
