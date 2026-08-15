"""Relative-volume confirmation mapped only to TQQQ/SOXL exposure."""

from __future__ import annotations

import argparse
import itertools
import json
import math
import time
from pathlib import Path
from typing import Any

import numpy as np
import search_full_universe_intraday_v11 as v11
import search_full_universe_intraday_v12_robustness as v12
import search_full_universe_intraday_v13_regime_rotation as v13
import search_full_universe_intraday_v15_prior5 as v15
import search_full_universe_intraday_v18_diversified_beam as v18

from us_intraday_lab.fast_intraday_research import metrics

DEVELOPMENT_NAMES = v15.DEVELOPMENT_NAMES
LEVERAGED = np.array((3, 4))
SLOTS = {
    "opening": ((5, 8), (15, 18, 23)),
    "morning": ((17, 23, 29), (36, 42, 47)),
    "midday": ((38, 41, 44), (50, 53, 56)),
    "afternoon": ((47, 53, 59), (66, 72, 77)),
    "late": ((68, 71, 74), (77,)),
}


class Cube(v15.Cube):
    """Exact execution cube with causal same-time relative volume."""

    def __init__(self, root: Path, source: str, boundary_tolerance: int) -> None:
        super().__init__(root, source, boundary_tolerance)
        if source == "alpaca":
            frame = v11._load_five_minute(root)
            volume = v11._cube(frame, self.sessions, "volume")
            cumulative = np.nancumsum(np.where(np.isfinite(volume), volume, 0.0), axis=1)
            self.relative_volume = np.full_like(cumulative, np.nan)
            for index in range(20, len(self.sessions)):
                median = np.nanmedian(cumulative[index - 20 : index], axis=0)
                self.relative_volume[index] = np.divide(
                    cumulative[index],
                    median,
                    out=np.full_like(median, np.nan),
                    where=median > 0,
                )
        else:
            self.relative_volume = np.full_like(self.opens, np.nan)

    def selected(self, specification: dict[str, Any]) -> np.ndarray:
        family = specification["family"]
        p = specification["parameters"]
        decision = int(p["decision"])
        feature = self._features(decision)
        current = feature["current"]
        recent = feature["recent"]
        pair = current[:, LEVERAGED]
        finite = np.isfinite(pair)
        if family == "leveraged_volume_momentum":
            selected = LEVERAGED[np.argmax(np.where(finite, pair, -np.inf), axis=1)]
            other = LEVERAGED[np.argmin(np.where(finite, pair, np.inf), axis=1)]
            value = current[self.rows, selected]
            eligible = (
                finite.all(axis=1)
                & (value >= float(p["current_floor"]))
                & (value - current[self.rows, other] >= float(p["relative_floor"]))
                & (self.relative_volume[self.rows, decision, selected] >= float(p["rvol_floor"]))
                & (self.relative_volume[:, decision, 0] >= float(p["spy_rvol_floor"]))
                & (self.prior_asset[self.rows, selected] >= float(p["prior5_floor"]))
                & (feature["spy"] >= float(p["spy_floor"]))
            )
        elif family == "leveraged_volume_recovery":
            selected = LEVERAGED[np.argmin(np.where(finite, pair, np.inf), axis=1)]
            value = current[self.rows, selected]
            eligible = (
                finite.all(axis=1)
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


def _specifications(slot: str):
    decisions, exits = SLOTS[slot]
    for decision, exit_bar in itertools.product(decisions, exits):
        if exit_bar <= decision + 2:
            continue
        for current, relative, rvol, spy_rvol, prior5, spy in itertools.product(
            (0.003, 0.006, 0.01, 0.015),
            (0.0, 0.003, 0.006),
            (0.7, 0.9, 1.1, 1.3),
            (0.7, 0.9, 1.1),
            (-0.10, -0.04, 0.0),
            (-0.01, 0.0),
        ):
            yield {
                "family": "leveraged_volume_momentum",
                "parameters": {
                    "slot": slot,
                    "decision": decision,
                    "exit": exit_bar,
                    "universe": "leveraged",
                    "current_floor": current,
                    "relative_floor": relative,
                    "rvol_floor": rvol,
                    "spy_rvol_floor": spy_rvol,
                    "prior5_floor": prior5,
                    "spy_floor": spy,
                },
            }
        for dip, recovery, rvol, spy_rvol, prior5, spy in itertools.product(
            (-0.006, -0.012, -0.02),
            (-0.003, 0.0, 0.004),
            (0.7, 1.0, 1.3),
            (0.7, 0.9, 1.1),
            (-0.10, -0.04, 0.0),
            (-0.02, -0.01, 0.0),
        ):
            yield {
                "family": "leveraged_volume_recovery",
                "parameters": {
                    "slot": slot,
                    "decision": decision,
                    "exit": exit_bar,
                    "universe": "leveraged",
                    "dip_ceiling": dip,
                    "recovery_floor": recovery,
                    "rvol_ceiling": rvol,
                    "spy_rvol_floor": spy_rvol,
                    "prior5_floor": prior5,
                    "spy_floor": spy,
                },
            }


def _normal_tail(value: float) -> float:
    return 0.5 * math.erfc(value / math.sqrt(2.0))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--beam-width", default=5000, type=int)
    args = parser.parse_args()
    started = time.perf_counter()
    v15.SLOTS = SLOTS
    v15._specifications = _specifications
    v18.SLOTS = SLOTS
    development = Cube(args.root, "alpaca", 0)
    shortlisted = {}
    sleeve_cells = {}
    for slot in SLOTS:
        shortlisted[slot], sleeve_cells[slot] = v18._shortlist(development, slot, 3, 25)
    frontier, portfolio_cells = v18._beam(development, shortlisted, args.beam_width, 5)
    for record in frontier:
        record["candidate_id"] = v12._identity(record["specifications"], "lev-v19p-")

    # Freeze above; consumed 2026 is attached only below.
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
        "selection_contract": "2022-2025 only; consumed 2026 post-freeze",
        "execution_contract": "TQQQ/SOXL long-only; gross<=1; no overnight; exact boundaries; <=5 non-overlapping sleeves",
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
