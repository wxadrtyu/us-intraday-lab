"""Causal VWAP reclaim and intraday range-structure search."""

from __future__ import annotations

import argparse
import itertools
import json
import math
import time
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import search_full_universe_intraday_v11 as v11
import search_full_universe_intraday_v12_robustness as v12
import search_full_universe_intraday_v13_regime_rotation as v13
import search_full_universe_intraday_v15_prior5 as v15
import search_full_universe_intraday_v18_diversified_beam as v18

from us_intraday_lab.fast_intraday_research import metrics

DEVELOPMENT_NAMES = v15.DEVELOPMENT_NAMES
UNIVERSES = {
    "risk": np.array((1, 2, 3, 4)),
    "sectors": np.arange(5, 16),
    "all": np.arange(1, 16),
}
SLOTS = {
    "opening": ((5, 8), (15, 18, 23)),
    "morning": ((17, 23, 29), (36, 42, 47)),
    "midday": ((38, 41, 44), (50, 53, 56)),
    "afternoon": ((47, 53, 59), (66, 72, 77)),
    "late": ((68, 71, 74), (77,)),
}


def _load_microstructure(root: Path, source: str):
    paths = v12._verified_paths(root, source)
    connection = duckdb.connect()
    try:
        return connection.execute(
            """
            WITH minute AS (
              SELECT *, date_diff(
                'minute', cast(session_date as timestamp) + interval '9 hours 30 minutes',
                timezone('America/New_York', timestamp)
              )::INTEGER AS minute_of_session
              FROM read_parquet(?)
            )
            SELECT symbol, session_date, floor(minute_of_session / 5)::INTEGER AS bar,
                   max(high) AS high, min(low) AS low,
                   sum(close * volume) AS close_dollar_volume,
                   sum(volume) AS volume
            FROM minute
            WHERE minute_of_session BETWEEN 0 AND 389
            GROUP BY symbol, session_date, bar
            ORDER BY session_date, bar, symbol
            """,
            [paths],
        ).fetch_df()
    finally:
        connection.close()


class Cube(v15.Cube):
    """Exact execution cube with causal session VWAP/range features."""

    def __init__(self, root: Path, source: str, boundary_tolerance: int) -> None:
        super().__init__(root, source, boundary_tolerance)
        frame = _load_microstructure(root, source)
        high = v11._cube(frame, self.sessions, "high")
        low = v11._cube(frame, self.sessions, "low")
        dollar = v11._cube(frame, self.sessions, "close_dollar_volume")
        volume = v11._cube(frame, self.sessions, "volume")
        finite_high = np.where(np.isfinite(high), high, -np.inf)
        finite_low = np.where(np.isfinite(low), low, np.inf)
        self.session_high = np.maximum.accumulate(finite_high, axis=1)
        self.session_low = np.minimum.accumulate(finite_low, axis=1)
        self.cumulative_dollar = np.nancumsum(dollar, axis=1)
        self.cumulative_volume = np.nancumsum(volume, axis=1)
        self.vwap = np.divide(
            self.cumulative_dollar,
            self.cumulative_volume,
            out=np.full_like(self.cumulative_dollar, np.nan),
            where=self.cumulative_volume > 0,
        )
        self._micro_cache: dict[int, dict[str, np.ndarray]] = {}

    def _micro(self, decision: int) -> dict[str, np.ndarray]:
        if decision in self._micro_cache:
            return self._micro_cache[decision]
        close = self.closes[:, decision, :]
        high = self.session_high[:, decision, :]
        low = self.session_low[:, decision, :]
        vwap = self.vwap[:, decision, :]
        price_vwap = (
            np.divide(
                close, vwap, out=np.full_like(close, np.nan), where=np.isfinite(vwap) & (vwap > 0)
            )
            - 1.0
        )
        low_vwap = (
            np.divide(
                low, vwap, out=np.full_like(low, np.nan), where=np.isfinite(vwap) & (vwap > 0)
            )
            - 1.0
        )
        recovery = (
            np.divide(
                close, low, out=np.full_like(close, np.nan), where=np.isfinite(low) & (low > 0)
            )
            - 1.0
        )
        spread = high - low
        close_location = np.divide(
            close - low,
            spread,
            out=np.full_like(close, np.nan),
            where=spread > 0,
        )
        session_range = (
            np.divide(high, low, out=np.full_like(high, np.nan), where=np.isfinite(low) & (low > 0))
            - 1.0
        )
        range_ratio = np.full_like(session_range, np.nan)
        for index in range(20, len(self.sessions)):
            median = np.nanmedian(session_range[index - 20 : index], axis=0)
            range_ratio[index] = np.divide(
                session_range[index],
                median,
                out=np.full_like(median, np.nan),
                where=median > 0,
            )
        output = {
            "price_vwap": price_vwap,
            "low_vwap": low_vwap,
            "recovery": recovery,
            "close_location": close_location,
            "session_range": session_range,
            "range_ratio": range_ratio,
        }
        self._micro_cache[decision] = output
        return output

    def selected(self, specification: dict[str, Any]) -> np.ndarray:
        family = specification["family"]
        p = specification["parameters"]
        decision = int(p["decision"])
        feature = self._features(decision)
        micro = self._micro(decision)
        current = feature["current"]
        universe = UNIVERSES[str(p["universe"])]
        finite = np.isfinite(current[:, universe])
        available = finite.sum(axis=1) >= max(2, len(universe) // 2)
        if family == "vwap_reclaim_rotation":
            subset = micro["recovery"][:, universe]
            selected = universe[np.argmax(np.where(np.isfinite(subset), subset, -np.inf), axis=1)]
            eligible = (
                available
                & (micro["low_vwap"][self.rows, selected] <= float(p["excursion_ceiling"]))
                & (micro["price_vwap"][self.rows, selected] >= float(p["vwap_floor"]))
                & (micro["recovery"][self.rows, selected] >= float(p["recovery_floor"]))
                & (micro["close_location"][self.rows, selected] >= float(p["close_location_floor"]))
                & (self.prior_asset[self.rows, selected] >= float(p["prior5_floor"]))
                & (feature["spy"] >= float(p["spy_floor"]))
            )
        elif family == "range_compression_breakout":
            selected = universe[np.argmax(np.where(finite, current[:, universe], -np.inf), axis=1)]
            eligible = (
                available
                & (current[self.rows, selected] >= float(p["current_floor"]))
                & (micro["price_vwap"][self.rows, selected] >= float(p["vwap_floor"]))
                & (micro["close_location"][self.rows, selected] >= float(p["close_location_floor"]))
                & (micro["range_ratio"][self.rows, selected] <= float(p["range_ratio_ceiling"]))
                & (self.prior_asset[self.rows, selected] >= float(p["prior5_floor"]))
                & (feature["spy"] >= float(p["spy_floor"]))
            )
        elif family == "vwap_support_momentum":
            selected = universe[np.argmax(np.where(finite, current[:, universe], -np.inf), axis=1)]
            eligible = (
                available
                & (current[self.rows, selected] >= float(p["current_floor"]))
                & (micro["low_vwap"][self.rows, selected] >= float(p["support_floor"]))
                & (micro["price_vwap"][self.rows, selected] >= float(p["vwap_floor"]))
                & (micro["close_location"][self.rows, selected] >= float(p["close_location_floor"]))
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
        for universe, excursion, vwap, recovery, location, prior5, spy in itertools.product(
            UNIVERSES,
            (-0.003, -0.006, -0.01),
            (-0.001, 0.0, 0.002),
            (0.003, 0.006, 0.01),
            (0.50, 0.70, 0.85),
            (-0.08, 0.0),
            (-0.01, 0.0),
        ):
            yield {
                "family": "vwap_reclaim_rotation",
                "parameters": {
                    "slot": slot,
                    "decision": decision,
                    "exit": exit_bar,
                    "universe": universe,
                    "excursion_ceiling": excursion,
                    "vwap_floor": vwap,
                    "recovery_floor": recovery,
                    "close_location_floor": location,
                    "prior5_floor": prior5,
                    "spy_floor": spy,
                },
            }
        for universe, current, vwap, location, ratio, prior5, spy in itertools.product(
            UNIVERSES,
            (0.003, 0.006, 0.01),
            (0.0, 0.002, 0.004),
            (0.70, 0.85, 0.95),
            (0.70, 1.0, 1.30),
            (-0.08, 0.0),
            (-0.01, 0.0),
        ):
            yield {
                "family": "range_compression_breakout",
                "parameters": {
                    "slot": slot,
                    "decision": decision,
                    "exit": exit_bar,
                    "universe": universe,
                    "current_floor": current,
                    "vwap_floor": vwap,
                    "close_location_floor": location,
                    "range_ratio_ceiling": ratio,
                    "prior5_floor": prior5,
                    "spy_floor": spy,
                },
            }
        for universe, current, support, vwap, location, prior5, spy in itertools.product(
            UNIVERSES,
            (0.003, 0.006, 0.01),
            (-0.006, -0.003, 0.0),
            (0.0, 0.002),
            (0.70, 0.85, 0.95),
            (-0.08, 0.0),
            (-0.01, 0.0),
        ):
            yield {
                "family": "vwap_support_momentum",
                "parameters": {
                    "slot": slot,
                    "decision": decision,
                    "exit": exit_bar,
                    "universe": universe,
                    "current_floor": current,
                    "support_floor": support,
                    "vwap_floor": vwap,
                    "close_location_floor": location,
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
        record["candidate_id"] = v12._identity(record["specifications"], "lev-v21p-")

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
        "selection_contract": "2022-2025 only; consumed 2026 and cross-source history post-freeze",
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
