"""Search non-overlapping two-sleeve portfolios from the v10 hypotheses.

The morning and afternoon development pools are ranked without consulting the
consumed 2026Q1 mask.  Diagnostic and execution stresses are attached only
after the portfolio frontier is frozen.
"""

from __future__ import annotations

import argparse
import hashlib
import heapq
import itertools
import json
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
from search_low_turnover_intraday_v10 import (
    DATASETS,
    SEGMENTS,
    STANDARD_COST,
    STRESS_COST,
    Search,
    _adjusted_p,
    _atomic_json,
    _folds,
    _neighbors,
    _primary_pass,
    _rank,
    _start_dates,
)

from us_intraday_lab.fast_intraday_research import metrics


def _identity(specifications: list[dict[str, Any]]) -> str:
    encoded = json.dumps(specifications, sort_keys=True, separators=(",", ":"))
    return "lev-v10p-" + hashlib.sha256(encoded.encode()).hexdigest()[:16]


def _morning_specifications(search: Search) -> Iterable[dict[str, Any]]:
    seen: set[str] = set()
    for base in search.specifications():
        decision = int(base["parameters"]["decision"])
        if decision not in (23, 35):
            continue
        for exit_bar in (47, 53, 59):
            if exit_bar <= decision + 6:
                continue
            specification = {
                "family": base["family"],
                "parameters": {**base["parameters"], "exit": exit_bar},
            }
            identity = json.dumps(specification, sort_keys=True, separators=(",", ":"))
            if identity not in seen:
                seen.add(identity)
                yield specification


def _afternoon_specifications(search: Search) -> Iterable[dict[str, Any]]:
    for specification in search.specifications():
        p = specification["parameters"]
        if int(p["decision"]) >= 47 and int(p["exit"]) >= 66:
            yield specification


def _portfolio_returns(
    search: Search,
    specifications: list[dict[str, Any]],
    *,
    cost: float = STANDARD_COST,
    delay: int = 0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    streams = [search.returns(spec, cost=cost, delay=delay) for spec in specifications]
    values = np.prod(1.0 + np.vstack([item[0] for item in streams]), axis=0) - 1.0
    benchmark = np.prod(1.0 + np.vstack([item[1] for item in streams]), axis=0) - 1.0
    active = np.logical_or.reduce([item[2] for item in streams])
    trades = np.sum(np.vstack([item[2] for item in streams]), axis=0)
    return values, benchmark, active, trades


def _observations(
    search: Search,
    specifications: list[dict[str, Any]],
    *,
    cost: float = STANDARD_COST,
    delay: int = 0,
) -> tuple[dict[str, dict[str, float | int]], np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    values, benchmark, active, trades = _portfolio_returns(
        search, specifications, cost=cost, delay=delay
    )
    names = (*SEGMENTS, "development_oos_2024_2025")
    result = {
        name: metrics(
            values[search.masks[name]], benchmark[search.masks[name]], active[search.masks[name]]
        )
        for name in names
    }
    result["development_oos_2024_2025"]["trades"] = int(
        trades[search.masks["development_oos_2024_2025"]].sum()
    )
    return result, values, benchmark, active, trades


def _shortlist(
    search: Search, specifications: Iterable[dict[str, Any]], top: int
) -> tuple[list[dict[str, Any]], int]:
    heaps: dict[str, list[tuple[tuple[float, float, float], int, dict[str, Any]]]] = {}
    scanned = 0
    serial = 0
    for spec in specifications:
        scanned += 1
        observations, _, _, _active = search.observations(spec)
        if any(
            int(observations[name]["trades"]) < minimum
            for name, minimum in zip(SEGMENTS, (20, 8, 8), strict=True)
        ):
            continue
        rank = _rank(observations)
        if min(rank) <= 0.0:
            continue
        family = str(spec["family"])
        item = (rank, serial, {"specification": spec, "rank": rank, "observations": observations})
        serial += 1
        heap = heaps.setdefault(family, [])
        if len(heap) < top:
            heapq.heappush(heap, item)
        elif item[:2] > heap[0][:2]:
            heapq.heapreplace(heap, item)
    output = [item[2] for heap in heaps.values() for item in heap]
    output.sort(key=lambda item: item["rank"], reverse=True)
    return output, scanned


def _portfolio_neighbors(search: Search, specifications: list[dict[str, Any]]) -> dict[str, Any]:
    records = []
    for sleeve_index, specification in enumerate(specifications):
        for neighbor in _neighbors(specification):
            changed = list(specifications)
            changed[sleeve_index] = neighbor
            first_exit = int(changed[0]["parameters"]["exit"])
            second_entry = int(changed[1]["parameters"]["decision"]) + 1
            if first_exit > second_entry:
                continue
            try:
                observation, _, _, _, _ = _observations(search, changed)
            except (IndexError, ValueError):
                continue
            records.append(
                {
                    "sleeve_index": sleeve_index,
                    "changed_specification": neighbor,
                    "development_oos": observation["development_oos_2024_2025"],
                    "primary_pass": _primary_pass(observation),
                }
            )
    fraction = (
        sum(bool(item["primary_pass"]) for item in records) / len(records) if records else 0.0
    )
    return {"count": len(records), "primary_pass_fraction": fraction, "neighbors": records}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--top-per-family-slot", type=int, default=30)
    parser.add_argument("--frontier-size", type=int, default=200)
    args = parser.parse_args()
    started = time.monotonic()
    search = Search(args.root)
    morning, morning_scanned = _shortlist(
        search, _morning_specifications(search), args.top_per_family_slot
    )
    afternoon, afternoon_scanned = _shortlist(
        search, _afternoon_specifications(search), args.top_per_family_slot
    )
    heap: list[tuple[tuple[float, float, float], int, dict[str, Any]]] = []
    combinations = 0
    development_hits = 0
    serial = 0
    for first, second in itertools.product(morning, afternoon):
        specifications = [first["specification"], second["specification"]]
        if (
            int(specifications[0]["parameters"]["exit"])
            > int(specifications[1]["parameters"]["decision"]) + 1
        ):
            continue
        combinations += 1
        observations, _, _, _, trades = _observations(search, specifications)
        rank = _rank(observations)
        if _primary_pass(observations):
            development_hits += 1
        record = {
            "candidate_id": _identity(specifications),
            "specifications": specifications,
            "development_rank": list(rank),
            "standard": observations,
            "development_trades": int(trades[search.masks["development_all"]].sum()),
        }
        item = (rank, serial, record)
        serial += 1
        if len(heap) < args.frontier_size:
            heapq.heappush(heap, item)
        elif item[:2] > heap[0][:2]:
            heapq.heapreplace(heap, item)

    # The portfolio frontier is fixed here, before any 2026Q1 metric is computed.
    frontier = [item[2] for item in heap]
    frontier.sort(key=lambda item: tuple(item["development_rank"]), reverse=True)
    total_trials = morning_scanned + afternoon_scanned + combinations
    diagnostic_mask = search.masks["consumed_2026q1_diagnostic"]
    pressure_pool = ThreadPoolExecutor(max_workers=2)
    for record in frontier:
        specifications = record["specifications"]
        standard, values, benchmark, active, _ = _observations(search, specifications)
        cost_future = pressure_pool.submit(_observations, search, specifications, cost=STRESS_COST)
        delay_future = pressure_pool.submit(_observations, search, specifications, delay=1)
        cost_stress, _, _, _, _ = cost_future.result()
        delay_stress, _, _, _, _ = delay_future.result()
        diagnostic = metrics(
            values[diagnostic_mask], benchmark[diagnostic_mask], active[diagnostic_mask]
        )
        folds = _folds(values, benchmark, active, search.masks["development_all"])
        starts = _start_dates(search, values, benchmark, active)
        neighbors = _portfolio_neighbors(search, specifications)
        multiple = _adjusted_p(values[search.masks["development_all"]], total_trials)
        record.update(
            {
                "standard": {**standard, "consumed_2026q1_diagnostic": diagnostic},
                "cost_18bp": cost_stress,
                "latency_one_bar_9bp": delay_stress,
                "development_folds": folds,
                "start_date_stress": starts,
                "parameter_neighborhood": neighbors,
                "multiple_comparison_pressure": {**multiple, "total_trials": total_trials},
            }
        )
        record["gates"] = {
            "standard_primary": _primary_pass(standard),
            "cost_18bp_primary": _primary_pass(cost_stress),
            "latency_one_bar_primary": _primary_pass(delay_stress),
            "four_of_five_positive_folds": sum(
                float(item["annualized_return"]) > 0.0 for item in folds
            )
            >= 4,
            "all_start_dates_positive": all(
                float(item["annualized_return"]) > 0.0 for item in starts.values()
            ),
            "parameter_neighborhood_70pct_primary": float(neighbors["primary_pass_fraction"])
            >= 0.70,
            "multiple_comparison_bonferroni_5pct": float(multiple["bonferroni_p"]) < 0.05,
            "consumed_2026q1_positive": float(diagnostic["annualized_return"]) > 0.0,
            "consumed_2026q1_mdd_below_20pct": float(diagnostic["max_drawdown"]) < 0.20,
        }
        record["eligible_for_future_simulation_observation"] = all(record["gates"].values())
    pressure_pool.shutdown()

    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "selection_contract": "morning/afternoon sleeves and portfolios ranked on 2022-2025 only; consumed 2026Q1 attached after frontier freeze",
        "portfolio_contract": "long only; no overnight; non-overlapping sleeves; maximum gross 1; no more than two round trips per session",
        "data_contract": {
            role: {"dataset_id": value[0], "content_sha256": value[1], "symbols": list(value[2])}
            for role, value in DATASETS.items()
        },
        "scan": {
            "morning_parameter_cells": morning_scanned,
            "afternoon_parameter_cells": afternoon_scanned,
            "morning_shortlist": len(morning),
            "afternoon_shortlist": len(afternoon),
            "portfolio_combinations": combinations,
            "development_primary_hits": development_hits,
            "frontier_size": len(frontier),
            "total_multiple_comparison_trials": total_trials,
            "elapsed_seconds": time.monotonic() - started,
            "pressure_workers": 2,
        },
        "simulation_observation_eligible_count": sum(
            bool(item["eligible_for_future_simulation_observation"]) for item in frontier
        ),
        "frontier": frontier,
    }
    _atomic_json(args.output, payload)
    print(
        json.dumps(
            {
                "scan": payload["scan"],
                "eligible": payload["simulation_observation_eligible_count"],
                "best": frontier[0] if frontier else None,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
