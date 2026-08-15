"""Fixed-asset intraday state search with a development-only frontier."""

from __future__ import annotations

import argparse
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
ASSETS = (1, 3, 4, 8, 10)
SLOTS = {
    "opening": ((2, 5, 8), (12, 15, 18, 23)),
    "morning": ((17, 23, 29), (36, 42, 47)),
    "midday": ((35, 38, 41, 44), (47, 50, 53, 56)),
    "afternoon": ((41, 47, 53), (59, 66, 72)),
    "late": ((59, 65, 71), (72, 77)),
}


class Cube(v15.Cube):
    """V15 cube extended with causal gap and previous-session state."""

    def __init__(self, root: Path, source: str, boundary_tolerance: int) -> None:
        super().__init__(root, source, boundary_tolerance)
        exact = (self.first[:, 0, :] <= boundary_tolerance) & (
            self.last[:, 77, :] >= 389 - boundary_tolerance
        )
        daily = np.where(exact, self.closes[:, 77, :] / self.opens[:, 0, :] - 1.0, np.nan)
        self.prior1 = np.full_like(daily, np.nan)
        self.prior_close = np.full_like(daily, np.nan)
        self.prior1[1:] = daily[:-1]
        self.prior_close[1:] = np.where(exact[:-1], self.closes[:-1, 77, :], np.nan)
        self.gap = self.opens[:, 0, :] / self.prior_close - 1.0

    def selected(self, specification: dict[str, Any]) -> np.ndarray:
        family = str(specification["family"])
        p = specification["parameters"]
        decision = int(p["decision"])
        asset = int(p["asset"])
        feature = self._features(decision)
        current = feature["current"][:, asset]
        recent = feature["recent"][:, asset]
        common = (
            np.isfinite(current)
            & np.isfinite(recent)
            & np.isfinite(self.gap[:, asset])
            & np.isfinite(self.prior_asset[:, asset])
            & (self.prior_asset[:, asset] >= float(p["prior5_floor"]))
            & (feature["spy"] >= float(p["spy_floor"]))
        )
        if family == "fixed_breakout":
            eligible = (
                common
                & (current >= float(p["current_floor"]))
                & (recent >= float(p["recent_floor"]))
                & (self.gap[:, asset] >= float(p["gap_floor"]))
            )
        elif family == "fixed_recovery":
            eligible = (
                common
                & (current <= float(p["dip_ceiling"]))
                & (recent >= float(p["recent_floor"]))
                & (self.gap[:, asset] <= float(p["gap_ceiling"]))
            )
        elif family == "gap_follow":
            eligible = (
                common
                & (self.gap[:, asset] >= float(p["gap_floor"]))
                & (current >= float(p["current_floor"]))
                & (current - feature["spy"] >= float(p["relative_floor"]))
            )
        else:
            raise ValueError(f"unsupported family: {family}")
        return np.where(eligible, asset, -1)


def _specifications(slot: str):
    decisions, exits = SLOTS[slot]
    for decision, exit_bar in itertools.product(decisions, exits):
        if exit_bar <= decision + 2:
            continue
        for asset, current, recent, gap, prior5, spy in itertools.product(
            ASSETS,
            (0.0, 0.004, 0.008, 0.015),
            (-0.003, 0.0, 0.004),
            (-0.02, 0.0, 0.01),
            (-0.08, 0.0, 0.04),
            (-0.01, 0.0, 0.003),
        ):
            yield {
                "family": "fixed_breakout",
                "parameters": {
                    "slot": slot,
                    "decision": decision,
                    "exit": exit_bar,
                    "asset": asset,
                    "universe": str(asset),
                    "current_floor": current,
                    "recent_floor": recent,
                    "gap_floor": gap,
                    "prior5_floor": prior5,
                    "spy_floor": spy,
                },
            }
        for asset, dip, recent, gap, prior5, spy in itertools.product(
            ASSETS,
            (-0.006, -0.012, -0.02),
            (-0.003, 0.0, 0.004),
            (0.0, 0.015, 0.03),
            (-0.08, 0.0, 0.04),
            (-0.02, -0.01, 0.0),
        ):
            yield {
                "family": "fixed_recovery",
                "parameters": {
                    "slot": slot,
                    "decision": decision,
                    "exit": exit_bar,
                    "asset": asset,
                    "universe": str(asset),
                    "dip_ceiling": dip,
                    "recent_floor": recent,
                    "gap_ceiling": gap,
                    "prior5_floor": prior5,
                    "spy_floor": spy,
                },
            }
        for asset, gap, current, relative, prior5, spy in itertools.product(
            ASSETS,
            (0.0, 0.008, 0.015),
            (-0.003, 0.0, 0.004),
            (0.0, 0.003, 0.006),
            (-0.08, 0.0, 0.04),
            (-0.01, 0.0, 0.003),
        ):
            yield {
                "family": "gap_follow",
                "parameters": {
                    "slot": slot,
                    "decision": decision,
                    "exit": exit_bar,
                    "asset": asset,
                    "universe": str(asset),
                    "gap_floor": gap,
                    "current_floor": current,
                    "relative_floor": relative,
                    "prior5_floor": prior5,
                    "spy_floor": spy,
                },
            }


def _observe_development(cube: Cube, stream: v12.ReturnStream) -> dict[str, Any]:
    masks = cube.masks()
    names = DEVELOPMENT_NAMES + ("development_oos_2024_2025",)
    return {
        name: metrics(
            stream.values[masks[name]], stream.benchmark[masks[name]], stream.active[masks[name]]
        )
        for name in names
    }


def _primary(observations: dict[str, Any]) -> bool:
    return v15._primary(observations)


def _normal_tail(value: float) -> float:
    return 0.5 * math.erfc(value / math.sqrt(2.0))


def _portfolio_beam(
    cube: Cube,
    shortlisted: dict[str, list[v13.Sleeve]],
    keep: int,
    max_sleeves: int,
) -> tuple[list[dict[str, Any]], int]:
    beam: list[tuple[tuple[float, float, float], int, tuple[v13.Sleeve, ...]]] = []
    serial = 0
    scanned = 0
    for slot in SLOTS:
        prefixes = [item[2] for item in beam] if beam else [()]
        expanded: list[tuple[tuple[float, float, float], int, tuple[v13.Sleeve, ...]]] = []
        for prefix in prefixes:
            options: list[v13.Sleeve | None] = [None, *shortlisted[slot]]
            for option in options:
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
                standard = v13._combine([item.standard for item in sleeves])
                cost = v13._combine(
                    [item.cost_18bp for item in sleeves if item.cost_18bp is not None]
                )
                delay = v13._combine(
                    [item.delay_5m for item in sleeves if item.delay_5m is not None]
                )
                standard_observation = _observe_development(cube, standard)
                cost_observation = _observe_development(cube, cost)
                delay_observation = _observe_development(cube, delay)
                rank = (
                    min(
                        float(standard_observation[name]["annualized_return"])
                        for name in DEVELOPMENT_NAMES
                    ),
                    min(
                        float(cost_observation["development_oos_2024_2025"]["annualized_return"]),
                        float(delay_observation["development_oos_2024_2025"]["annualized_return"]),
                    ),
                    min(
                        float(cost_observation["development_oos_2024_2025"]["information_ratio"]),
                        float(delay_observation["development_oos_2024_2025"]["information_ratio"]),
                    ),
                )
                expanded.append((rank, serial, sleeves))
                serial += 1
        expanded.sort(key=lambda item: (item[0], item[1]), reverse=True)
        unique: dict[str, tuple[tuple[float, float, float], int, tuple[v13.Sleeve, ...]]] = {}
        for item in expanded:
            identity = v12._identity([sleeve.specification for sleeve in item[2]], "lev-v17p-")
            unique.setdefault(identity, item)
            if len(unique) >= keep:
                break
        beam = list(unique.values())
    records = []
    for rank, _, sleeves in beam:
        records.append(
            {
                "candidate_id": v12._identity(
                    [item.specification for item in sleeves], "lev-v17p-"
                ),
                "specifications": [item.specification for item in sleeves],
                "development_rank": list(rank),
            }
        )
    return records, scanned


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--top-per-group", default=4, type=int)
    parser.add_argument("--frontier-size", default=2000, type=int)
    parser.add_argument("--max-sleeves", default=5, type=int)
    args = parser.parse_args()
    started = time.perf_counter()
    development = Cube(args.root, "alpaca", 0)

    original_observe = v13._observe
    v13.DEVELOPMENT_NAMES = DEVELOPMENT_NAMES
    v13.SLOTS = SLOTS
    v13._specifications = _specifications
    v13._primary = _primary
    v13._observe = _observe_development
    shortlisted: dict[str, list[v13.Sleeve]] = {}
    sleeve_cells: dict[str, int] = {}
    for slot in SLOTS:
        shortlisted[slot], sleeve_cells[slot] = v13._shortlist(
            development, slot, args.top_per_group
        )
    frontier, portfolio_cells = _portfolio_beam(
        development, shortlisted, args.frontier_size, args.max_sleeves
    )
    v13._observe = original_observe

    # Only the frozen frontier reaches the consumed and historical replay.
    historical = Cube(args.root, "historical", 0)
    masks = development.masks()
    fold_indices = np.array_split(np.flatnonzero(masks["development_all"]), 5)
    total_trials = sum(sleeve_cells.values()) + portfolio_cells
    eligible = 0
    diagnostic_hits = 0
    for record in frontier:
        specs = record["specifications"]
        standard_stream = v13._combine([development.replay_spec(spec) for spec in specs])
        standard = original_observe(development, standard_stream)
        cost = original_observe(
            development,
            v13._combine([development.replay_spec(spec, 0.0018) for spec in specs]),
        )
        delay = original_observe(
            development,
            v13._combine([development.replay_spec(spec, 0.0009, 1) for spec in specs]),
        )
        historical_observation = original_observe(
            historical,
            v13._combine([historical.replay_spec(spec) for spec in specs]),
        )
        folds = [
            metrics(
                standard_stream.values[index],
                standard_stream.benchmark[index],
                standard_stream.active[index],
            )
            for index in fold_indices
        ]
        oos = standard["development_oos_2024_2025"]
        consumed = standard["consumed_2026_all"]
        hist = historical_observation["historical_2018_2020"]
        z_score = float(oos["information_ratio"]) * math.sqrt(max(1, int(oos["trades"])) / 252)
        bonferroni = min(1.0, 2.0 * _normal_tail(abs(z_score)) * max(1, total_trials))
        gates = {
            "standard_primary": _primary(standard),
            "cost_18bp_primary": _primary(cost),
            "delay_5min_primary": _primary(delay),
            "four_of_five_positive_folds": sum(
                float(item["annualized_return"]) > 0 for item in folds
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
                "development_folds": folds,
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
        "selection_contract": "2022-2025 only; consumed 2026 and cross-source history post-freeze",
        "execution_contract": "long-only; gross<=1; no overnight; exact scheduled boundaries; <=3 non-overlapping sleeves",
        "datasets": {"alpaca": v12.ALPACA, "historical": v12.HISTORICAL},
        "scan": {
            "sleeve_cells": sleeve_cells,
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
