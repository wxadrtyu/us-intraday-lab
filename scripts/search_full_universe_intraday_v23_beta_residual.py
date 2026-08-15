"""Rolling-beta residual strength and recovery rotation search."""

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
import search_full_universe_intraday_v18_diversified_beam as v18
import search_full_universe_intraday_v21_vwap_structure as v21

from us_intraday_lab.fast_intraday_research import metrics

DEVELOPMENT_NAMES = v15.DEVELOPMENT_NAMES
UNIVERSES = v21.UNIVERSES
SLOTS = v21.SLOTS
CUBE_CLASS: type[Cube] | None = None
CANDIDATE_PREFIX = "lev-v23p-"


class Cube(v15.Cube):
    """Exact cube with beta estimates ending at the prior session."""

    def __init__(self, root: Path, source: str, boundary_tolerance: int) -> None:
        super().__init__(root, source, boundary_tolerance)
        exact = (self.first[:, 0, :] <= boundary_tolerance) & (
            self.last[:, 77, :] >= 389 - boundary_tolerance
        )
        daily = np.where(exact, self.closes[:, 77, :] / self.opens[:, 0, :] - 1.0, np.nan)
        self.beta = np.full_like(daily, np.nan)
        for index in range(60, len(self.sessions)):
            window = daily[index - 60 : index]
            market = window[:, 0]
            for asset in range(len(v12.SYMBOLS)):
                valid = np.isfinite(market) & np.isfinite(window[:, asset])
                if valid.sum() < 40:
                    continue
                market_valid = market[valid]
                variance = float(np.var(market_valid, ddof=1))
                if variance <= 1e-12:
                    continue
                self.beta[index, asset] = float(
                    np.cov(window[valid, asset], market_valid, ddof=1)[0, 1] / variance
                )
        self.beta[:, 0] = 1.0

    def selected(self, specification: dict[str, Any]) -> np.ndarray:
        family = specification["family"]
        p = specification["parameters"]
        decision = int(p["decision"])
        feature = self._features(decision)
        current = feature["current"]
        recent = feature["recent"]
        universe = UNIVERSES[str(p["universe"])]
        residual = current - self.beta * feature["spy"][:, None]
        spy_recent = recent[:, 0]
        recent_residual = recent - self.beta * spy_recent[:, None]
        prior5_residual = self.prior_asset - self.beta * self.prior_spy[:, None]
        finite = np.isfinite(residual[:, universe])
        available = finite.sum(axis=1) >= max(2, len(universe) // 2)
        if family == "beta_residual_strength":
            selected = universe[np.argmax(np.where(finite, residual[:, universe], -np.inf), axis=1)]
            eligible = (
                available
                & (residual[self.rows, selected] >= float(p["residual_floor"]))
                & (current[self.rows, selected] >= float(p["current_floor"]))
                & (recent_residual[self.rows, selected] >= float(p["recent_residual_floor"]))
                & (prior5_residual[self.rows, selected] >= float(p["prior5_residual_floor"]))
                & (feature["spy"] >= float(p["spy_floor"]))
            )
        elif family == "beta_residual_recovery":
            selected = universe[np.argmin(np.where(finite, residual[:, universe], np.inf), axis=1)]
            eligible = (
                available
                & (residual[self.rows, selected] <= float(p["residual_ceiling"]))
                & (recent_residual[self.rows, selected] >= float(p["recovery_floor"]))
                & (current[self.rows, selected] >= float(p["current_floor"]))
                & (prior5_residual[self.rows, selected] >= float(p["prior5_residual_floor"]))
                & (feature["spy"] >= float(p["spy_floor"]))
            )
        elif family == "defensive_beta_rotation":
            subset_beta = self.beta[:, universe]
            selected = universe[
                np.argmin(np.where(np.isfinite(subset_beta), subset_beta, np.inf), axis=1)
            ]
            eligible = (
                available
                & (feature["spy"] <= float(p["spy_ceiling"]))
                & (feature["spy"] >= float(p["spy_floor"]))
                & (residual[self.rows, selected] >= float(p["residual_floor"]))
                & (recent_residual[self.rows, selected] >= float(p["recent_residual_floor"]))
                & (self.beta[self.rows, selected] <= float(p["beta_ceiling"]))
            )
        else:
            raise ValueError(f"unsupported family: {family}")
        return np.where(eligible, selected, -1)


def _specifications(slot: str):
    decisions, exits = SLOTS[slot]
    for decision, exit_bar in itertools.product(decisions, exits):
        if exit_bar <= decision + 2:
            continue
        for universe, residual, current, recent, prior5, spy in itertools.product(
            UNIVERSES,
            (0.002, 0.004, 0.007, 0.01),
            (-0.003, 0.0, 0.003),
            (-0.003, 0.0, 0.003),
            (-0.05, 0.0, 0.03),
            (-0.01, 0.0),
        ):
            yield {
                "family": "beta_residual_strength",
                "parameters": {
                    "slot": slot,
                    "decision": decision,
                    "exit": exit_bar,
                    "universe": universe,
                    "residual_floor": residual,
                    "current_floor": current,
                    "recent_residual_floor": recent,
                    "prior5_residual_floor": prior5,
                    "spy_floor": spy,
                },
            }
        for universe, residual, recovery, current, prior5, spy in itertools.product(
            UNIVERSES,
            (-0.003, -0.006, -0.01, -0.015),
            (-0.003, 0.0, 0.003, 0.006),
            (-0.01, -0.003, 0.0),
            (-0.05, 0.0, 0.03),
            (-0.015, -0.005, 0.0),
        ):
            yield {
                "family": "beta_residual_recovery",
                "parameters": {
                    "slot": slot,
                    "decision": decision,
                    "exit": exit_bar,
                    "universe": universe,
                    "residual_ceiling": residual,
                    "recovery_floor": recovery,
                    "current_floor": current,
                    "prior5_residual_floor": prior5,
                    "spy_floor": spy,
                },
            }
        for universe, spy_floor, spy_ceiling, residual, recent, beta in itertools.product(
            ("risk", "sectors", "all"),
            (-0.02, -0.01),
            (-0.003, 0.0, 0.003),
            (-0.003, 0.0, 0.003),
            (-0.003, 0.0, 0.003),
            (0.8, 1.0, 1.2),
        ):
            yield {
                "family": "defensive_beta_rotation",
                "parameters": {
                    "slot": slot,
                    "decision": decision,
                    "exit": exit_bar,
                    "universe": universe,
                    "spy_floor": spy_floor,
                    "spy_ceiling": spy_ceiling,
                    "residual_floor": residual,
                    "recent_residual_floor": recent,
                    "beta_ceiling": beta,
                },
            }


def _normal_tail(value: float) -> float:
    return 0.5 * math.erfc(value / math.sqrt(2.0))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--beam-width", default=4000, type=int)
    args = parser.parse_args()
    started = time.perf_counter()
    v15.SLOTS = SLOTS
    v15._specifications = _specifications
    v18.SLOTS = SLOTS
    cube_class = CUBE_CLASS or Cube
    development = cube_class(args.root, "alpaca", 0)
    shortlisted = {}
    sleeve_cells = {}
    for slot in SLOTS:
        shortlisted[slot], sleeve_cells[slot] = v18._shortlist(development, slot, 2, 20)
    frontier, portfolio_cells = v18._beam(development, shortlisted, args.beam_width, 5)
    for record in frontier:
        record["candidate_id"] = v12._identity(record["specifications"], CANDIDATE_PREFIX)

    historical = cube_class(args.root, "historical", 0)
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
        "selection_contract": "rolling beta and all ranking use information through 2025 only",
        "execution_contract": "long-only; gross<=1; no overnight; exact boundaries; <=5 non-overlapping sleeves",
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
                    "historical": best["historical_cross_source"]["historical_2018_2020"],
                    "consumed_2026": best["standard"]["consumed_2026_all"],
                    "gates": best["gates"],
                },
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
