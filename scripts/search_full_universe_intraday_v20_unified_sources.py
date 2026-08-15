"""Unified development-only beam across three distinct intraday sources."""

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
import search_full_universe_intraday_v17_fixed_asset_state as v17
import search_full_universe_intraday_v18_diversified_beam as v18
import search_full_universe_intraday_v19_volume_leveraged as v19

from us_intraday_lab.fast_intraday_research import metrics

DEVELOPMENT_NAMES = v15.DEVELOPMENT_NAMES
FIVE_SLOTS = dict(v17.SLOTS)
SEVEN_SLOTS = {
    "opening": ((2, 5), (12, 15)),
    "early_morning": ((17, 23), (29, 36)),
    "late_morning": ((29, 35), (41, 47)),
    "midday": ((44, 47), (53, 56)),
    "afternoon": ((53, 59), (66,)),
    "late_afternoon": ((65, 68), (72,)),
    "close": ((71, 74), (77,)),
}
SLOTS = FIVE_SLOTS
UNIVERSES = {
    "risk": np.array((1, 2, 3, 4)),
    "sectors": np.arange(5, 16),
    "all": np.arange(1, 16),
}


class VolumeCube(v19.Cube):
    """Generic ETF rotation with causal relative-volume confirmation."""

    def selected(self, specification: dict[str, Any]) -> np.ndarray:
        family = specification["family"]
        p = specification["parameters"]
        decision = int(p["decision"])
        feature = self._features(decision)
        current = feature["current"]
        recent = feature["recent"]
        universe = UNIVERSES[str(p["universe"])]
        subset = current[:, universe]
        finite = np.isfinite(subset)
        if family == "volume_momentum_rotation":
            selected = universe[np.argmax(np.where(finite, subset, -np.inf), axis=1)]
            value = current[self.rows, selected]
            eligible = (
                (finite.sum(axis=1) >= max(2, len(universe) // 2))
                & (value >= float(p["current_floor"]))
                & (value - feature["spy"] >= float(p["relative_floor"]))
                & (self.relative_volume[self.rows, decision, selected] >= float(p["rvol_floor"]))
                & (self.relative_volume[:, decision, 0] >= float(p["spy_rvol_floor"]))
                & (self.prior_asset[self.rows, selected] >= float(p["prior5_floor"]))
                & (feature["spy"] >= float(p["spy_floor"]))
            )
        elif family == "volume_recovery_rotation":
            selected = universe[np.argmin(np.where(finite, subset, np.inf), axis=1)]
            value = current[self.rows, selected]
            eligible = (
                (finite.sum(axis=1) >= max(2, len(universe) // 2))
                & (value <= float(p["dip_ceiling"]))
                & (recent[self.rows, selected] >= float(p["recovery_floor"]))
                & (self.relative_volume[self.rows, decision, selected] <= float(p["rvol_ceiling"]))
                & (self.relative_volume[:, decision, 0] >= float(p["spy_rvol_floor"]))
                & (self.prior_asset[self.rows, selected] >= float(p["prior5_floor"]))
                & (feature["spy"] >= float(p["spy_floor"]))
            )
        else:
            raise ValueError(f"unsupported family: {family}")
        return np.where(eligible, selected, -1)


def _volume_specifications(slot: str):
    decisions, exits = SLOTS[slot]
    for decision, exit_bar in itertools.product(decisions, exits):
        if exit_bar <= decision + 2:
            continue
        for universe, current, relative, rvol, spy_rvol, prior5, spy in itertools.product(
            UNIVERSES,
            (0.003, 0.006, 0.01, 0.015),
            (0.0, 0.003, 0.006),
            (0.8, 1.0, 1.25),
            (0.8, 1.0, 1.2),
            (-0.08, 0.0),
            (-0.01, 0.0),
        ):
            yield {
                "family": "volume_momentum_rotation",
                "parameters": {
                    "slot": slot,
                    "decision": decision,
                    "exit": exit_bar,
                    "universe": universe,
                    "current_floor": current,
                    "relative_floor": relative,
                    "rvol_floor": rvol,
                    "spy_rvol_floor": spy_rvol,
                    "prior5_floor": prior5,
                    "spy_floor": spy,
                },
            }
        for universe, dip, recovery, rvol, spy_rvol, prior5, spy in itertools.product(
            UNIVERSES,
            (-0.006, -0.012, -0.02),
            (-0.003, 0.0, 0.004),
            (0.7, 1.0, 1.3),
            (0.8, 1.0, 1.2),
            (-0.08, 0.0),
            (-0.02, -0.01, 0.0),
        ):
            yield {
                "family": "volume_recovery_rotation",
                "parameters": {
                    "slot": slot,
                    "decision": decision,
                    "exit": exit_bar,
                    "universe": universe,
                    "dip_ceiling": dip,
                    "recovery_floor": recovery,
                    "rvol_ceiling": rvol,
                    "spy_rvol_floor": spy_rvol,
                    "prior5_floor": prior5,
                    "spy_floor": spy,
                },
            }


def _merge(sources: list[list[v13.Sleeve]], per_criterion: int) -> list[v13.Sleeve]:
    unique = {
        v12._identity(sleeve.specification, "lev-v20s-"): sleeve
        for source in sources
        for sleeve in source
    }
    selected = {}
    for criterion in DEVELOPMENT_NAMES + ("development_oos_2024_2025",):
        ordered = sorted(
            unique.values(),
            key=lambda sleeve: (
                float(sleeve.observations[criterion]["annualized_return"]),
                float(sleeve.observations[criterion]["information_ratio"]),
            ),
            reverse=True,
        )
        for sleeve in ordered[:per_criterion]:
            selected[v12._identity(sleeve.specification, "lev-v20s-")] = sleeve
    return list(selected.values())


def _dispatch(
    prior_cube: v15.Cube,
    fixed_cube: v17.Cube,
    volume_cube: VolumeCube,
    specification: dict[str, Any],
    cost: float = 0.0009,
    delay: int = 0,
) -> v12.ReturnStream:
    family = specification["family"]
    if family in {"relative_strength_rotation", "pullback_recovery_rotation"}:
        return prior_cube.replay_spec(specification, cost, delay)
    if family in {"fixed_breakout", "fixed_recovery", "gap_follow"}:
        return fixed_cube.replay_spec(specification, cost, delay)
    return volume_cube.replay_spec(specification, cost, delay)


def _normal_tail(value: float) -> float:
    return 0.5 * math.erfc(value / math.sqrt(2.0))


def main() -> None:
    global SLOTS
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--beam-width", default=3000, type=int)
    parser.add_argument("--layout", choices=("five", "seven"), default="five")
    args = parser.parse_args()
    started = time.perf_counter()
    SLOTS = FIVE_SLOTS if args.layout == "five" else SEVEN_SLOTS
    v15.SLOTS = SLOTS
    v17.SLOTS = SLOTS
    v18.SLOTS = SLOTS
    prior_cube = v15.Cube(args.root, "alpaca", 0)
    fixed_cube = v17.Cube(args.root, "alpaca", 0)
    volume_cube = VolumeCube(args.root, "alpaca", 0)
    shortlisted = {}
    sleeve_cells: dict[str, dict[str, int]] = {}
    prior_specifications = v15._specifications
    for slot in SLOTS:
        v15._specifications = prior_specifications
        prior, prior_cells = v18._shortlist(prior_cube, slot, 1, 10)
        v15._specifications = v17._specifications
        fixed, fixed_cells = v18._shortlist(fixed_cube, slot, 1, 10)
        v15._specifications = _volume_specifications
        volume, volume_cells = v18._shortlist(volume_cube, slot, 1, 10)
        shortlisted[slot] = _merge([prior, fixed, volume], 15)
        sleeve_cells[slot] = {
            "prior5": prior_cells,
            "fixed": fixed_cells,
            "volume": volume_cells,
        }
    max_sleeves = 5 if args.layout == "five" else 7
    frontier, portfolio_cells = v18._beam(prior_cube, shortlisted, args.beam_width, max_sleeves)
    for record in frontier:
        record["candidate_id"] = v12._identity(record["specifications"], "lev-v20p-")

    # Development beam frozen above; 2026 attached below.
    masks = prior_cube.masks()
    folds = np.array_split(np.flatnonzero(masks["development_all"]), 5)
    total_sleeves = sum(sum(item.values()) for item in sleeve_cells.values())
    total_trials = total_sleeves + portfolio_cells
    eligible = 0
    diagnostic_hits = 0
    for record in frontier:
        specs = record["specifications"]
        standard_stream = v13._combine(
            [_dispatch(prior_cube, fixed_cube, volume_cube, spec) for spec in specs]
        )
        standard = v13._observe(prior_cube, standard_stream)
        cost = v13._observe(
            prior_cube,
            v13._combine(
                [_dispatch(prior_cube, fixed_cube, volume_cube, spec, 0.0018) for spec in specs]
            ),
        )
        delay = v13._observe(
            prior_cube,
            v13._combine(
                [_dispatch(prior_cube, fixed_cube, volume_cube, spec, 0.0009, 1) for spec in specs]
            ),
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
            "consumed_2026_total_above_20pct": float(consumed["total_return"]) > 0.20,
            "consumed_2026_mdd_below_20pct": float(consumed["max_drawdown"]) < 0.20,
            "consumed_2026_ir_at_least_1": float(consumed["information_ratio"]) >= 1.0,
            "multiple_comparison_bonferroni_5pct": bonferroni < 0.05,
            "historical_cross_source_evaluated": False,
            "start_date_stress_evaluated": False,
            "parameter_neighborhood_evaluated": False,
        }
        record.update(
            {
                "standard": standard,
                "cost_18bp": cost,
                "delay_5min_9bp": delay,
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
        "selection_contract": "three source shortlists and unified beam use 2022-2025 only",
        "execution_contract": "long-only; gross<=1; no overnight; exact boundaries; <=5 non-overlapping sleeves",
        "scan": {
            "sleeve_cells": sleeve_cells,
            "merged_shortlisted": {key: len(value) for key, value in shortlisted.items()},
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
                    "cost_oos": best["cost_18bp"]["development_oos_2024_2025"],
                    "delay_oos": best["delay_5min_9bp"]["development_oos_2024_2025"],
                    "consumed_2026": best["standard"]["consumed_2026_all"],
                    "gates": best["gates"],
                },
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
