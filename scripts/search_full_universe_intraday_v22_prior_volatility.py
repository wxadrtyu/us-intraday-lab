"""Prior-session volatility-state reversal and continuation search."""

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


class Cube(v21.Cube):
    """Microstructure cube with strictly prior-session volatility state."""

    def __init__(self, root: Path, source: str, boundary_tolerance: int) -> None:
        super().__init__(root, source, boundary_tolerance)
        high = self.session_high[:, 77, :]
        low = self.session_low[:, 77, :]
        close = self.closes[:, 77, :]
        open_ = self.opens[:, 0, :]
        daily_return = close / open_ - 1.0
        daily_range = (
            np.divide(high, low, out=np.full_like(high, np.nan), where=np.isfinite(low) & (low > 0))
            - 1.0
        )
        spread = high - low
        close_location = np.divide(
            close - low,
            spread,
            out=np.full_like(close, np.nan),
            where=np.isfinite(spread) & (spread > 0),
        )
        self.prior_return = np.full_like(daily_return, np.nan)
        self.prior_range_ratio = np.full_like(daily_range, np.nan)
        self.prior_close_location = np.full_like(close_location, np.nan)
        self.prior_return[1:] = daily_return[:-1]
        self.prior_close_location[1:] = close_location[:-1]
        for index in range(21, len(self.sessions)):
            median = np.nanmedian(daily_range[index - 21 : index - 1], axis=0)
            self.prior_range_ratio[index] = np.divide(
                daily_range[index - 1],
                median,
                out=np.full_like(median, np.nan),
                where=median > 0,
            )

    def selected(self, specification: dict[str, Any]) -> np.ndarray:
        family = specification["family"]
        p = specification["parameters"]
        decision = int(p["decision"])
        feature = self._features(decision)
        current = feature["current"]
        recent = feature["recent"]
        universe = UNIVERSES[str(p["universe"])]
        finite = np.isfinite(current[:, universe])
        available = finite.sum(axis=1) >= max(2, len(universe) // 2)
        if family == "market_aftershock_recovery":
            selected = universe[np.argmax(np.where(finite, current[:, universe], -np.inf), axis=1)]
            eligible = (
                available
                & (self.prior_return[:, 0] <= float(p["prior_spy_ceiling"]))
                & (self.prior_range_ratio[:, 0] >= float(p["prior_range_floor"]))
                & (self.prior_close_location[:, 0] <= float(p["prior_close_location_ceiling"]))
                & (current[self.rows, selected] >= float(p["current_floor"]))
                & (recent[self.rows, selected] >= float(p["recent_floor"]))
                & (feature["spy"] >= float(p["spy_floor"]))
            )
        elif family == "asset_aftershock_reversal":
            prior_subset = self.prior_return[:, universe]
            selected = universe[
                np.argmin(np.where(np.isfinite(prior_subset), prior_subset, np.inf), axis=1)
            ]
            eligible = (
                available
                & (self.prior_return[self.rows, selected] <= float(p["prior_asset_ceiling"]))
                & (self.prior_range_ratio[self.rows, selected] >= float(p["prior_range_floor"]))
                & (current[self.rows, selected] >= float(p["current_floor"]))
                & (recent[self.rows, selected] >= float(p["recent_floor"]))
                & (feature["spy"] >= float(p["spy_floor"]))
            )
        elif family == "calm_trend_continuation":
            selected = universe[np.argmax(np.where(finite, current[:, universe], -np.inf), axis=1)]
            eligible = (
                available
                & (self.prior_range_ratio[:, 0] <= float(p["prior_range_ceiling"]))
                & (self.prior_return[:, 0] >= float(p["prior_spy_floor"]))
                & (self.prior_asset[self.rows, selected] >= float(p["prior5_floor"]))
                & (current[self.rows, selected] >= float(p["current_floor"]))
                & (current[self.rows, selected] - feature["spy"] >= float(p["relative_floor"]))
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
        for universe, shock, range_floor, location, current, recent, spy in itertools.product(
            UNIVERSES,
            (-0.005, -0.01, -0.02),
            (1.0, 1.30, 1.60),
            (0.30, 0.50, 0.70),
            (0.0, 0.003, 0.006),
            (-0.003, 0.0, 0.003),
            (-0.01, 0.0),
        ):
            yield {
                "family": "market_aftershock_recovery",
                "parameters": {
                    "slot": slot,
                    "decision": decision,
                    "exit": exit_bar,
                    "universe": universe,
                    "prior_spy_ceiling": shock,
                    "prior_range_floor": range_floor,
                    "prior_close_location_ceiling": location,
                    "current_floor": current,
                    "recent_floor": recent,
                    "spy_floor": spy,
                },
            }
        for universe, shock, range_floor, current, recent, spy in itertools.product(
            UNIVERSES,
            (-0.01, -0.02, -0.04),
            (1.0, 1.30, 1.60),
            (-0.003, 0.0, 0.003, 0.006),
            (-0.003, 0.0, 0.003),
            (-0.01, 0.0),
        ):
            yield {
                "family": "asset_aftershock_reversal",
                "parameters": {
                    "slot": slot,
                    "decision": decision,
                    "exit": exit_bar,
                    "universe": universe,
                    "prior_asset_ceiling": shock,
                    "prior_range_floor": range_floor,
                    "current_floor": current,
                    "recent_floor": recent,
                    "spy_floor": spy,
                },
            }
        for universe, range_ceiling, prior_spy, prior5, current, relative, spy in itertools.product(
            UNIVERSES,
            (0.60, 0.80, 1.0),
            (-0.005, 0.0, 0.005),
            (-0.08, 0.0),
            (0.003, 0.006, 0.01),
            (0.0, 0.003, 0.006),
            (-0.01, 0.0),
        ):
            yield {
                "family": "calm_trend_continuation",
                "parameters": {
                    "slot": slot,
                    "decision": decision,
                    "exit": exit_bar,
                    "universe": universe,
                    "prior_range_ceiling": range_ceiling,
                    "prior_spy_floor": prior_spy,
                    "prior5_floor": prior5,
                    "current_floor": current,
                    "relative_floor": relative,
                    "spy_floor": spy,
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
    development = Cube(args.root, "alpaca", 0)
    shortlisted = {}
    sleeve_cells = {}
    for slot in SLOTS:
        shortlisted[slot], sleeve_cells[slot] = v18._shortlist(development, slot, 2, 20)
    frontier, portfolio_cells = v18._beam(development, shortlisted, args.beam_width, 5)
    for record in frontier:
        record["candidate_id"] = v12._identity(record["specifications"], "lev-v22p-")

    historical = Cube(args.root, "historical", 0)
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
        "selection_contract": "2022-2025 only; consumed 2026 and history post-freeze",
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
