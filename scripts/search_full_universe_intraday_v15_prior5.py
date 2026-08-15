"""Development-frozen prior-five-day ETF rotation search.

The 2026 interval is attached only after the 2022-2025 frontier is frozen.
"""

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

from us_intraday_lab.fast_intraday_research import metrics

DEVELOPMENT_NAMES = ("train_2022_2023", "2024", "2025")
SLOTS = {
    "opening": ((2, 5, 8), (12, 15, 18, 23)),
    "morning": ((17, 23, 29), (36, 42, 47)),
    "afternoon": ((47, 53, 59), (66, 72, 77)),
    "late": ((68, 71, 74), (77,)),
}


class Cube(v13.Cube):
    """Exact-boundary cube with causal five-session asset state."""

    def __init__(self, root: Path, source: str, boundary_tolerance: int) -> None:
        super().__init__(root, source, boundary_tolerance)
        exact = (self.first[:, 0, :] <= boundary_tolerance) & (
            self.last[:, 77, :] >= 389 - boundary_tolerance
        )
        daily = np.where(exact, self.closes[:, 77, :] / self.opens[:, 0, :] - 1.0, np.nan)
        prior5 = np.full_like(daily, np.nan)
        for index in range(5, len(self.sessions)):
            window = daily[index - 5 : index]
            valid = np.isfinite(window).all(axis=0)
            prior5[index, valid] = np.prod(1.0 + window[:, valid], axis=0) - 1.0
        self.prior_asset = prior5
        self.prior_spy = prior5[:, 0]

    def masks(self) -> dict[str, np.ndarray]:
        masks = super().masks()
        if self.source != "alpaca":
            return masks
        years = self.dates.year.to_numpy()
        masks["train_2022_2023"] = (years >= 2022) & (years <= 2023)
        masks["development_all"] = (years >= 2022) & (years <= 2025)
        return masks


def _specifications(slot: str):
    decisions, exits = SLOTS[slot]
    for decision, exit_bar in itertools.product(decisions, exits):
        if exit_bar <= decision + 2:
            continue
        for universe, current, relative, prior_asset, prior_spy, spy in itertools.product(
            v13.UNIVERSES,
            (0.0, 0.003, 0.006, 0.01, 0.015, 0.02),
            (0.0, 0.003, 0.006, 0.01),
            (-0.10, -0.05, 0.0, 0.03),
            (-0.10, -0.05, 0.0, 0.03),
            (-0.015, -0.005, 0.0, 0.003),
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
            v13.UNIVERSES,
            (-0.006, -0.01, -0.015, -0.02, -0.03),
            (-0.003, 0.0, 0.003, 0.006),
            (-0.10, -0.05, 0.0, 0.03),
            (-0.10, -0.05, 0.0, 0.03),
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


def _primary(observations: dict[str, dict[str, float | int]]) -> bool:
    oos = observations["development_oos_2024_2025"]
    return (
        float(oos["annualized_return"]) >= 0.50
        and float(oos["max_drawdown"]) < 0.20
        and float(oos["information_ratio"]) >= 1.0
        and all(float(observations[name]["annualized_return"]) > 0 for name in DEVELOPMENT_NAMES)
    )


def _normal_tail(value: float) -> float:
    return 0.5 * math.erfc(value / math.sqrt(2.0))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--boundary-tolerance-minutes", choices=(0, 1), default=0, type=int)
    parser.add_argument("--top-per-group", default=6, type=int)
    parser.add_argument("--frontier-size", default=1000, type=int)
    args = parser.parse_args()
    started = time.perf_counter()

    # Reuse the vectorized v13 beam with the v15 development contract and grid.
    v13.DEVELOPMENT_NAMES = DEVELOPMENT_NAMES
    v13.SLOTS = SLOTS
    v13._specifications = _specifications
    v13._primary = _primary
    development = Cube(args.root, "alpaca", args.boundary_tolerance_minutes)
    shortlisted: dict[str, list[v13.Sleeve]] = {}
    sleeve_cells: dict[str, int] = {}
    for slot in SLOTS:
        shortlisted[slot], sleeve_cells[slot] = v13._shortlist(
            development, slot, args.top_per_group
        )
    frontier, portfolio_cells = v13._portfolio_frontier(
        development, shortlisted, args.frontier_size
    )
    for record in frontier:
        record["candidate_id"] = v12._identity(record["specifications"], "lev-v15p-")

    # Freeze above. Diagnostics below cannot affect membership or order.
    historical = Cube(args.root, "historical", args.boundary_tolerance_minutes)
    masks = development.masks()
    dev_all = masks["development_all"]
    fold_indices = np.array_split(np.flatnonzero(dev_all), 5)
    total_trials = sum(sleeve_cells.values()) + portfolio_cells
    eligible = 0
    diagnostic_hits = 0
    for record in frontier:
        specs = record["specifications"]
        standard = v13._combine([development.replay_spec(spec) for spec in specs])
        historical_stream = v13._combine([historical.replay_spec(spec) for spec in specs])
        record["standard"] = v13._observe(development, standard)
        record["historical_cross_source"] = v13._observe(historical, historical_stream)
        record["development_folds"] = [
            metrics(standard.values[index], standard.benchmark[index], standard.active[index])
            for index in fold_indices
        ]
        oos = record["standard"]["development_oos_2024_2025"]
        consumed = record["standard"]["consumed_2026_all"]
        hist = record["historical_cross_source"]["historical_2018_2020"]
        z_score = float(oos["information_ratio"]) * math.sqrt(max(1, int(oos["trades"])) / 252)
        bonferroni = min(1.0, 2.0 * _normal_tail(abs(z_score)) * max(1, total_trials))
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
            "multiple_comparison_bonferroni_5pct": bonferroni < 0.05,
        }
        record["multiple_comparison"] = {"bonferroni_p": bonferroni, "total_trials": total_trials}
        record["gates"] = gates
        record["eligible_for_future_simulation_observation"] = all(gates.values())
        diagnostic_hits += int(gates["consumed_2026_total_above_20pct"])
        eligible += int(record["eligible_for_future_simulation_observation"])

    payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "selection_contract": "2022-2025 only; 2018-2020 and consumed 2026 post-freeze",
        "execution_contract": "long-only; gross<=1; no overnight; scheduled five-minute boundaries",
        "boundary_tolerance_minutes": args.boundary_tolerance_minutes,
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
    best = max(
        frontier,
        key=lambda item: float(item["standard"]["consumed_2026_all"]["total_return"]),
        default=None,
    )
    print(
        json.dumps(
            {"scan": payload["scan"], "diagnostic_hits": diagnostic_hits, "eligible": eligible}
        )
    )
    if best:
        print(
            json.dumps(
                {
                    "best_id": best["candidate_id"],
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
