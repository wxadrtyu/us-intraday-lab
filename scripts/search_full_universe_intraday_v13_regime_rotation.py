"""Development-only v13 regime/rotation search with post-freeze diagnostics."""

from __future__ import annotations

import argparse
import heapq
import itertools
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import search_full_universe_intraday_v12_robustness as v12

from us_intraday_lab.fast_intraday_research import metrics

STANDARD_COST = 0.0009
STRESS_COST = 0.0018
DEVELOPMENT_NAMES = ("train_2021_2023", "2024", "2025")
UNIVERSES = {
    "risk": np.array((1, 2, 3, 4)),
    "sectors": np.arange(5, 16),
    "all": np.arange(1, 16),
}
SLOTS = {
    "opening": ((2, 5, 8), (12, 15, 18, 23)),
    "morning": ((17, 23, 29), (36, 42, 47)),
    "afternoon": ((47, 53, 59), (66, 72, 77)),
    "late": ((68, 71), (77,)),
}


@dataclass(slots=True)
class Sleeve:
    specification: dict[str, Any]
    standard: v12.ReturnStream
    cost_18bp: v12.ReturnStream | None
    delay_5m: v12.ReturnStream | None
    observations: dict[str, dict[str, float | int]]
    rank: tuple[float, float, float]


class Cube(v12.ResearchCube):
    """V12 exact-boundary cube plus causal prior-session asset state."""

    def __init__(self, root: Path, source: str, boundary_tolerance: int) -> None:
        super().__init__(root, source, boundary_tolerance)
        exact = (self.first[:, 0, :] <= boundary_tolerance) & (
            self.last[:, 77, :] >= 389 - boundary_tolerance
        )
        daily = np.where(exact, self.closes[:, 77, :] / self.opens[:, 0, :] - 1.0, np.nan)
        self.prior_asset = np.full_like(daily, np.nan)
        self.prior_asset[1:] = daily[:-1]
        self.prior_spy = self.prior_asset[:, 0]

    def selected(self, specification: dict[str, Any]) -> np.ndarray:
        family = str(specification["family"])
        p = specification["parameters"]
        decision = int(p["decision"])
        feature = self._features(decision)
        current = feature["current"]
        recent = feature["recent"]
        universe = UNIVERSES[str(p["universe"])]
        subset = current[:, universe]
        finite = np.isfinite(subset)
        if family == "relative_strength_rotation":
            local = np.argmax(np.where(finite, subset, -np.inf), axis=1)
            selected = universe[local]
            value = current[self.rows, selected]
            eligible = (
                np.isfinite(value)
                & (finite.sum(axis=1) >= max(2, len(universe) // 2))
                & (value >= float(p["current_floor"]))
                & (value - feature["spy"] >= float(p["relative_floor"]))
                & (self.prior_asset[self.rows, selected] >= float(p["prior_asset_floor"]))
                & (self.prior_spy >= float(p["prior_spy_floor"]))
                & (feature["spy"] >= float(p["spy_floor"]))
            )
        elif family == "pullback_recovery_rotation":
            local = np.argmin(np.where(finite, subset, np.inf), axis=1)
            selected = universe[local]
            value = current[self.rows, selected]
            eligible = (
                np.isfinite(value)
                & np.isfinite(recent[self.rows, selected])
                & (finite.sum(axis=1) >= max(2, len(universe) // 2))
                & (value <= float(p["dip_ceiling"]))
                & (recent[self.rows, selected] >= float(p["recovery_floor"]))
                & (self.prior_asset[self.rows, selected] >= float(p["prior_asset_floor"]))
                & (self.prior_spy >= float(p["prior_spy_floor"]))
                & (feature["spy"] >= float(p["spy_floor"]))
            )
        else:
            raise ValueError(f"unsupported family: {family}")
        return np.where(eligible, selected, -1)

    def replay_spec(
        self, specification: dict[str, Any], cost: float = STANDARD_COST, delay: int = 0
    ) -> v12.ReturnStream:
        p = specification["parameters"]
        entry = int(p["decision"]) + 1 + delay
        exit_bar = int(p["exit"])
        if entry >= exit_bar:
            raise ValueError("entry must precede exit")
        selected = self.selected(specification)
        safe = np.maximum(selected, 0)
        active = selected >= 0
        tolerance = self.boundary_tolerance
        active &= (
            (self.first[self.rows, entry, safe] <= entry * 5 + tolerance)
            & (self.first[self.rows, exit_bar, safe] <= exit_bar * 5 + tolerance)
            & (self.first[:, entry, 0] <= entry * 5 + tolerance)
            & (self.first[:, exit_bar, 0] <= exit_bar * 5 + tolerance)
        )
        values = np.zeros(len(self.sessions))
        for asset in range(1, len(v12.SYMBOLS)):
            mask = active & (selected == asset)
            values[mask] = (
                self.opens[mask, exit_bar, asset] / self.opens[mask, entry, asset] - 1.0 - cost
            )
        benchmark = np.where(
            active, self.opens[:, exit_bar, 0] / self.opens[:, entry, 0] - 1.0, 0.0
        )
        return v12.ReturnStream(values, benchmark, active, active.astype(int))


def _observe(cube: Cube, stream: v12.ReturnStream) -> dict[str, dict[str, float | int]]:
    return {
        name: metrics(stream.values[mask], stream.benchmark[mask], stream.active[mask])
        for name, mask in cube.masks().items()
        if mask.any()
    }


def _rank(observations: dict[str, dict[str, float | int]]) -> tuple[float, float, float]:
    return (
        min(float(observations[name]["annualized_return"]) for name in DEVELOPMENT_NAMES),
        float(observations["development_oos_2024_2025"]["annualized_return"]),
        float(observations["development_oos_2024_2025"]["information_ratio"]),
    )


def _primary(observations: dict[str, dict[str, float | int]]) -> bool:
    oos = observations["development_oos_2024_2025"]
    return (
        float(oos["annualized_return"]) >= 0.50
        and float(oos["max_drawdown"]) < 0.20
        and float(oos["information_ratio"]) >= 1.0
        and all(float(observations[name]["annualized_return"]) > 0 for name in DEVELOPMENT_NAMES)
    )


def _specifications(slot: str):
    decisions, exits = SLOTS[slot]
    for decision, exit_bar in itertools.product(decisions, exits):
        if exit_bar <= decision + 2:
            continue
        for universe, current, relative, prior_asset, prior_spy, spy in itertools.product(
            UNIVERSES,
            (0.003, 0.006, 0.01, 0.015, 0.02),
            (0.0, 0.003, 0.006),
            (-0.06, -0.03, 0.0),
            (-0.04, -0.02, 0.0),
            (-0.01, 0.0, 0.003),
        ):
            yield {
                "family": "relative_strength_rotation",
                "parameters": {
                    "slot": slot,
                    "decision": decision,
                    "exit": exit_bar,
                    "universe": universe,
                    "current_floor": current,
                    "relative_floor": relative,
                    "prior_asset_floor": prior_asset,
                    "prior_spy_floor": prior_spy,
                    "spy_floor": spy,
                },
            }
        for universe, dip, recovery, prior_asset, prior_spy, spy in itertools.product(
            UNIVERSES,
            (-0.006, -0.01, -0.015, -0.02, -0.03),
            (-0.003, 0.0, 0.003, 0.006),
            (-0.06, -0.03, 0.0),
            (-0.04, -0.02, 0.0),
            (-0.02, -0.01, 0.0),
        ):
            yield {
                "family": "pullback_recovery_rotation",
                "parameters": {
                    "slot": slot,
                    "decision": decision,
                    "exit": exit_bar,
                    "universe": universe,
                    "dip_ceiling": dip,
                    "recovery_floor": recovery,
                    "prior_asset_floor": prior_asset,
                    "prior_spy_floor": prior_spy,
                    "spy_floor": spy,
                },
            }


def _shortlist(cube: Cube, slot: str, size: int) -> tuple[list[Sleeve], int]:
    heaps: dict[str, list[tuple[tuple[float, float, float], int, Sleeve]]] = {}
    scanned = 0
    serial = 0
    for specification in _specifications(slot):
        scanned += 1
        standard = cube.replay_spec(specification)
        observations = _observe(cube, standard)
        if any(
            int(observations[name]["trades"]) < minimum
            for name, minimum in zip(DEVELOPMENT_NAMES, (10, 3, 3), strict=True)
        ):
            continue
        rank = _rank(observations)
        if rank[0] <= 0:
            continue
        sleeve = Sleeve(specification, standard, None, None, observations, rank)
        p = specification["parameters"]
        group = f"{specification['family']}:{p['decision']}:{p['exit']}:{p['universe']}"
        heap = heaps.setdefault(group, [])
        item = (rank, serial, sleeve)
        serial += 1
        if len(heap) < size:
            heapq.heappush(heap, item)
        elif item[:2] > heap[0][:2]:
            heapq.heapreplace(heap, item)
    unique: dict[str, Sleeve] = {}
    for heap in heaps.values():
        for _, _, sleeve in heap:
            unique[v12._identity(sleeve.specification, "lev-v13s-")] = sleeve
    stressed = []
    for sleeve in unique.values():
        sleeve.cost_18bp = cube.replay_spec(sleeve.specification, STRESS_COST)
        sleeve.delay_5m = cube.replay_spec(sleeve.specification, STANDARD_COST, 1)
        cost_obs = _observe(cube, sleeve.cost_18bp)
        delay_obs = _observe(cube, sleeve.delay_5m)
        stress_return = min(
            float(cost_obs["development_oos_2024_2025"]["annualized_return"]),
            float(delay_obs["development_oos_2024_2025"]["annualized_return"]),
        )
        stress_ir = min(
            float(cost_obs["development_oos_2024_2025"]["information_ratio"]),
            float(delay_obs["development_oos_2024_2025"]["information_ratio"]),
        )
        sleeve.rank = (sleeve.rank[0], stress_return, stress_ir)
        stressed.append(sleeve)
    stressed.sort(key=lambda item: item.rank, reverse=True)
    return stressed[: max(20, size * 4)], scanned


def _combine(streams: list[v12.ReturnStream]) -> v12.ReturnStream:
    return v12.ReturnStream(
        np.prod(1.0 + np.vstack([item.values for item in streams]), axis=0) - 1.0,
        np.prod(1.0 + np.vstack([item.benchmark for item in streams]), axis=0) - 1.0,
        np.logical_or.reduce([item.active for item in streams]),
        np.vstack([item.component_trades for item in streams]).sum(axis=0),
    )


def _portfolio_frontier(
    cube: Cube, shortlisted: dict[str, list[Sleeve]], size: int
) -> tuple[list[dict[str, Any]], int]:
    heap: list[tuple[tuple[float, float, float], int, dict[str, Any]]] = []
    serial = 0
    scanned = 0
    labels = tuple(name for name in SLOTS if shortlisted[name])
    layouts = [(name,) for name in labels]
    layouts += list(itertools.combinations(labels, 2))
    layouts += list(itertools.combinations(labels, 3))
    for layout in layouts:
        for sleeves in itertools.product(*(shortlisted[name] for name in layout)):
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
            standard = _combine([item.standard for item in sleeves])
            cost = _combine([item.cost_18bp for item in sleeves if item.cost_18bp is not None])
            delay = _combine([item.delay_5m for item in sleeves if item.delay_5m is not None])
            standard_obs = _observe(cube, standard)
            cost_obs = _observe(cube, cost)
            delay_obs = _observe(cube, delay)
            weakest = min(
                float(standard_obs[name]["annualized_return"]) for name in DEVELOPMENT_NAMES
            )
            stress_return = min(
                float(cost_obs["development_oos_2024_2025"]["annualized_return"]),
                float(delay_obs["development_oos_2024_2025"]["annualized_return"]),
            )
            stress_ir = min(
                float(cost_obs["development_oos_2024_2025"]["information_ratio"]),
                float(delay_obs["development_oos_2024_2025"]["information_ratio"]),
            )
            rank = (weakest, stress_return, stress_ir)
            record = {
                "candidate_id": v12._identity(
                    [item.specification for item in sleeves], "lev-v13p-"
                ),
                "specifications": [item.specification for item in sleeves],
                "development_rank": list(rank),
                "standard": standard_obs,
                "cost_18bp": cost_obs,
                "delay_5min_9bp": delay_obs,
                "development_active_sessions": int(standard.active.sum()),
                "development_component_trades": int(standard.component_trades.sum()),
            }
            item = (rank, serial, record)
            serial += 1
            if len(heap) < size:
                heapq.heappush(heap, item)
            elif item[:2] > heap[0][:2]:
                heapq.heapreplace(heap, item)
    return [item[2] for item in sorted(heap, reverse=True)], scanned


def _normal_tail(value: float) -> float:
    return 0.5 * math.erfc(value / math.sqrt(2.0))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--boundary-tolerance-minutes", choices=(0, 1), default=0, type=int)
    parser.add_argument("--top-per-group", default=4, type=int)
    parser.add_argument("--frontier-size", default=500, type=int)
    args = parser.parse_args()
    started = time.perf_counter()
    development = Cube(args.root, "alpaca", args.boundary_tolerance_minutes)
    shortlisted: dict[str, list[Sleeve]] = {}
    sleeve_cells: dict[str, int] = {}
    for slot in SLOTS:
        shortlisted[slot], sleeve_cells[slot] = _shortlist(development, slot, args.top_per_group)
    frontier, portfolio_cells = _portfolio_frontier(development, shortlisted, args.frontier_size)
    # The frontier is now frozen. Only this block may attach consumed periods.
    historical = Cube(args.root, "historical", args.boundary_tolerance_minutes)
    masks = development.masks()
    dev_all = masks["development_all"]
    fold_indices = np.array_split(np.flatnonzero(dev_all), 5)
    eligible = 0
    for record in frontier:
        specs = record["specifications"]
        standard = _combine([development.replay_spec(spec) for spec in specs])
        historical_stream = _combine([historical.replay_spec(spec) for spec in specs])
        record["standard"] = _observe(development, standard)
        record["historical_cross_source"] = _observe(historical, historical_stream)
        record["development_folds"] = [
            metrics(standard.values[index], standard.benchmark[index], standard.active[index])
            for index in fold_indices
        ]
        oos = record["standard"]["development_oos_2024_2025"]
        consumed = record["standard"]["consumed_2026_all"]
        hist = record["historical_cross_source"]["historical_2018_2020"]
        gates = {
            "standard_primary": _primary(record["standard"]),
            "cost_18bp_primary": _primary(record["cost_18bp"]),
            "delay_5min_primary": _primary(record["delay_5min_9bp"]),
            "four_of_five_positive_folds": sum(
                float(item["annualized_return"]) > 0 for item in record["development_folds"]
            )
            >= 4,
            "historical_positive_mdd_below_20pct": (
                float(hist["annualized_return"]) > 0 and float(hist["max_drawdown"]) < 0.20
            ),
            "consumed_2026_total_above_20pct": float(consumed["total_return"]) > 0.20,
            "consumed_2026_mdd_below_20pct": float(consumed["max_drawdown"]) < 0.20,
            "consumed_2026_ir_at_least_1": float(consumed["information_ratio"]) >= 1.0,
        }
        z_score = float(oos["information_ratio"]) * math.sqrt(max(1, int(oos["trades"])) / 252.0)
        raw_p = 2.0 * _normal_tail(abs(z_score))
        gates["multiple_comparison_bonferroni_5pct"] = (
            raw_p * max(1, sum(sleeve_cells.values()) + portfolio_cells) < 0.05
        )
        record["multiple_comparison"] = {
            "raw_normal_p": raw_p,
            "bonferroni_p": min(1.0, raw_p * max(1, sum(sleeve_cells.values()) + portfolio_cells)),
        }
        record["gates"] = gates
        record["eligible_for_future_simulation_observation"] = all(gates.values())
        eligible += int(record["eligible_for_future_simulation_observation"])
    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "selection_contract": "2021-2025 only; 2018-2020 and consumed 2026 post-freeze",
        "execution_contract": "long-only; gross<=1; no overnight; exact scheduled boundaries",
        "boundary_tolerance_minutes": args.boundary_tolerance_minutes,
        "datasets": {"alpaca": v12.ALPACA, "historical": v12.HISTORICAL},
        "scan": {
            "sleeve_cells": sleeve_cells,
            "portfolio_cells": portfolio_cells,
            "frontier_size": len(frontier),
            "elapsed_seconds": time.perf_counter() - started,
        },
        "eligible_count": eligible,
        "frontier": frontier,
    }
    v12._atomic(args.output, payload)
    print(json.dumps({"scan": payload["scan"], "eligible_count": eligible}, sort_keys=True))
    if frontier:
        best = max(
            frontier,
            key=lambda item: float(item["standard"]["consumed_2026_all"]["total_return"]),
        )
        print(
            json.dumps(
                {
                    "best_2026_after_freeze": best["candidate_id"],
                    "standard_oos": best["standard"]["development_oos_2024_2025"],
                    "consumed_2026": best["standard"]["consumed_2026_all"],
                    "gates": best["gates"],
                },
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
