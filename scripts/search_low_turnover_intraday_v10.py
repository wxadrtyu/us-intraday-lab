"""Checkpointed low-turnover search with a consumed 2026Q1 diagnostic.

Ranking is completed on 2022-2025 before the diagnostic mask is evaluated.
Only explicitly allow-listed, content-addressed snapshots are accepted.
"""

from __future__ import annotations

import argparse
import hashlib
import heapq
import itertools
import json
import math
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

from us_intraday_lab.fast_intraday_research import metrics

DATASETS = {
    "pair_development": (
        "hf-finnhub-5min-138ddc27bc3de530051d01e30087e449",
        "b7c75247b26a0958777148946932de2b58f605343395ac0f38aba0a0dd8ba56b",
        ("TQQQ", "SOXL"),
    ),
    "spy_development": (
        "hf-finnhub-5min-b78802459222d4baef0985e726232461",
        "31a2c567e20121a2055305d868786c91e6fdc12c0166ff29b1b76e46dda70211",
        ("SPY",),
    ),
    "pair_diagnostic": (
        "hf-finnhub-5min-50ac3b84b79898a4e0d4ee63cc4947dc",
        "9eb2e4b91f2a6e1ab642710901efe234c556d107b6bf204bf62224e5bdd7aa01",
        ("TQQQ", "SOXL"),
    ),
    "spy_diagnostic": (
        "hf-finnhub-5min-28a0c165f75db0eadc0953192212663b",
        "96bdda963eae00d77e609da72be182c376e2d789405f0978df7d0d27c6120181",
        ("SPY",),
    ),
}

STANDARD_COST = 0.0009
STRESS_COST = 0.0018
SYMBOLS = ("TQQQ", "SOXL")
SEGMENTS = ("train_2022_2023", "2024", "2025")


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _dataset_dir(root: Path, role: str) -> Path:
    dataset_id, expected_hash, _ = DATASETS[role]
    directory = root / "data" / "lake" / "long_horizon" / "canonical" / dataset_id
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("dataset_id") != dataset_id:
        raise ValueError(f"{role} dataset identity mismatch")
    if manifest.get("content_sha256") != expected_hash:
        raise ValueError(f"{role} content identity mismatch")
    return directory


def _load(root: Path, role: str) -> pd.DataFrame:
    directory = _dataset_dir(root, role)
    _, _, symbols = DATASETS[role]
    pattern = (directory / "sessions" / "*.parquet").as_posix()
    quoted = ",".join(f"'{symbol}'" for symbol in symbols)
    connection = duckdb.connect()
    try:
        frame = connection.execute(
            f"""
            SELECT symbol, session_date, timestamp, open, high, low, close, volume
            FROM read_parquet(?)
            WHERE symbol IN ({quoted})
            ORDER BY session_date, timestamp, symbol
            """,
            [pattern],
        ).fetch_df()
    finally:
        connection.close()
    counts = frame.groupby(["session_date", "symbol"], observed=True).size().unstack()
    good = counts.index[(counts.reindex(columns=symbols) == 78).all(axis=1)]
    return frame.loc[frame["session_date"].isin(good)].copy()


def _combine(first: pd.DataFrame, second: pd.DataFrame) -> pd.DataFrame:
    return (
        pd.concat([first, second], ignore_index=True)
        .drop_duplicates(["session_date", "timestamp", "symbol"], keep="first")
        .sort_values(["session_date", "timestamp", "symbol"], kind="stable")
    )


def _cube(
    frame: pd.DataFrame, sessions: pd.Index, symbols: tuple[str, ...], column: str
) -> np.ndarray:
    ordered = frame.sort_values(["session_date", "timestamp", "symbol"], kind="stable").copy()
    ordered["bar"] = ordered.groupby(["session_date", "symbol"], observed=True).cumcount()
    wide = ordered.pivot(index=["session_date", "bar"], columns="symbol", values=column)
    wide = wide.reindex(pd.MultiIndex.from_product([sessions, range(78)]), columns=symbols)
    values = wide.to_numpy(dtype=float).reshape(len(sessions), 78, len(symbols))
    if not np.isfinite(values).all():
        raise ValueError(f"non-finite {column} cube")
    return values


def _candidate_id(specification: dict[str, Any]) -> str:
    encoded = json.dumps(specification, sort_keys=True, separators=(",", ":"))
    return "lev-v10-" + hashlib.sha256(encoded.encode()).hexdigest()[:16]


def _normal_tail(value: float) -> float:
    return 0.5 * math.erfc(value / math.sqrt(2.0))


class Search:
    def __init__(self, root: Path) -> None:
        pair = _combine(_load(root, "pair_development"), _load(root, "pair_diagnostic"))
        spy = _combine(_load(root, "spy_development"), _load(root, "spy_diagnostic"))
        self.sessions = pd.Index(sorted(set(pair["session_date"]) & set(spy["session_date"])))
        pair = pair.loc[pair["session_date"].isin(self.sessions)]
        spy = spy.loc[spy["session_date"].isin(self.sessions)]
        self.opens = _cube(pair, self.sessions, SYMBOLS, "open")
        self.highs = _cube(pair, self.sessions, SYMBOLS, "high")
        self.lows = _cube(pair, self.sessions, SYMBOLS, "low")
        self.closes = _cube(pair, self.sessions, SYMBOLS, "close")
        self.spy_open = _cube(spy, self.sessions, ("SPY",), "open")[:, :, 0]
        self.spy_close = _cube(spy, self.sessions, ("SPY",), "close")[:, :, 0]
        dates = pd.to_datetime(self.sessions.astype(str))
        years = dates.year.to_numpy()
        self.masks = {
            "train_2022_2023": years <= 2023,
            "2024": years == 2024,
            "2025": years == 2025,
            "development_oos_2024_2025": (years == 2024) | (years == 2025),
            "consumed_2026q1_diagnostic": years == 2026,
            "development_all": years <= 2025,
        }
        self.rows = np.arange(len(self.sessions))
        self.prior_spy = np.concatenate(
            [[np.nan], self.spy_close[:-1, -1] / self.spy_open[:-1, 0] - 1.0]
        )
        self.family_trials: dict[str, int] = {}

    def signal(self, spec: dict[str, Any]) -> np.ndarray:
        family = str(spec["family"])
        p = spec["parameters"]
        decision = int(p["decision"])
        current = self.closes[:, decision, :] / self.opens[:, 0, :] - 1.0
        spy_current = self.spy_close[:, decision] / self.spy_open[:, 0] - 1.0
        stronger = np.argmax(current, axis=1)
        weaker = np.argmin(current, axis=1)
        if family == "failed_breakdown_recovery":
            low_excursion = self.lows[:, : decision + 1, :].min(axis=1) / self.opens[:, 0, :] - 1.0
            asset = np.argmin(low_excursion, axis=1)
            recovery = (
                self.closes[:, decision, :] / self.lows[:, : decision + 1, :].min(axis=1) - 1.0
            )
            recent = self.closes[:, decision, :] / self.closes[:, decision - 6, :] - 1.0
            eligible = (
                (low_excursion[self.rows, asset] <= float(p["low_ceiling"]))
                & (recovery[self.rows, asset] >= float(p["recovery_floor"]))
                & (current[self.rows, asset] <= float(p["current_ceiling"]))
                & (recent[self.rows, asset] >= float(p["recent_floor"]))
                & (spy_current >= float(p["spy_floor"]))
            )
        elif family == "relative_laggard_recovery":
            recent = self.closes[:, decision, :] / self.closes[:, decision - 6, :] - 1.0
            relative = current[self.rows, weaker] - current[self.rows, stronger]
            asset = weaker
            eligible = (
                (relative <= float(p["relative_ceiling"]))
                & (recent[self.rows, asset] >= float(p["recent_floor"]))
                & (current[self.rows, asset] >= float(p["current_floor"]))
                & (spy_current >= float(p["spy_floor"]))
                & (self.prior_spy >= float(p["prior_spy_floor"]))
            )
        elif family == "contraction_relative_breakout":
            asset = stronger
            recent = self.closes[:, decision, :] / self.closes[:, decision - 6, :] - 1.0
            relative = current[self.rows, asset] - current[self.rows, weaker]
            recent_range = (
                self.highs[:, decision - 5 : decision + 1, :].max(axis=1)
                / self.lows[:, decision - 5 : decision + 1, :].min(axis=1)
                - 1.0
            )
            earlier_range = (
                self.highs[:, decision - 17 : decision - 5, :].max(axis=1)
                / self.lows[:, decision - 17 : decision - 5, :].min(axis=1)
                - 1.0
            )
            contraction = recent_range / np.maximum(earlier_range, 1e-12)
            eligible = (
                (current[self.rows, asset] >= float(p["current_floor"]))
                & (relative >= float(p["relative_floor"]))
                & (recent[self.rows, asset] >= float(p["recent_floor"]))
                & (contraction[self.rows, asset] <= float(p["contraction_ceiling"]))
                & (spy_current >= float(p["spy_floor"]))
            )
        elif family == "regime_selective_rotation":
            asset = stronger
            relative = current[self.rows, asset] - current[self.rows, weaker]
            range_low = self.lows[:, : decision + 1, :].min(axis=1)
            range_high = self.highs[:, : decision + 1, :].max(axis=1)
            position = (self.closes[:, decision, :] - range_low) / np.maximum(
                range_high - range_low, 1e-12
            )
            eligible = (
                (current[self.rows, asset] >= float(p["current_floor"]))
                & (relative >= float(p["relative_floor"]))
                & (position[self.rows, asset] >= float(p["range_position_floor"]))
                & (spy_current >= float(p["spy_floor"]))
                & (self.prior_spy >= float(p["prior_spy_floor"]))
            )
        else:
            raise ValueError(f"unsupported family: {family}")
        return np.where(eligible, asset, -1)

    def returns(
        self, spec: dict[str, Any], *, cost: float = STANDARD_COST, delay: int = 0
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        selected = self.signal(spec)
        p = spec["parameters"]
        entry = int(p["decision"]) + 1 + delay
        exit_bar = int(p["exit"])
        if entry >= exit_bar:
            raise ValueError("entry must precede exit")
        active = selected >= 0
        values = np.zeros(len(self.sessions))
        benchmark = np.zeros(len(self.sessions))
        for asset in range(2):
            mask = selected == asset
            values[mask] = (
                self.opens[mask, exit_bar, asset] / self.opens[mask, entry, asset] - 1.0 - cost
            )
        benchmark[active] = self.spy_open[active, exit_bar] / self.spy_open[active, entry] - 1.0
        return values, benchmark, active

    def observations(
        self, spec: dict[str, Any], *, cost: float = STANDARD_COST, delay: int = 0
    ) -> tuple[dict[str, dict[str, float | int]], np.ndarray, np.ndarray, np.ndarray]:
        values, benchmark, active = self.returns(spec, cost=cost, delay=delay)
        names = (*SEGMENTS, "development_oos_2024_2025")
        result = {
            name: metrics(
                values[self.masks[name]], benchmark[self.masks[name]], active[self.masks[name]]
            )
            for name in names
        }
        return result, values, benchmark, active

    def specifications(self) -> Iterable[dict[str, Any]]:
        for decision, exit_bar in itertools.product((23, 35, 47, 59), (60, 66, 72, 77)):
            if exit_bar <= decision + 6:
                continue
            for low, recovery, ceiling, recent, spy_floor in itertools.product(
                (-0.01, -0.016, -0.022, -0.03, -0.04),
                (0.006, 0.01, 0.015, 0.022),
                (-0.01, 0.0, 0.01),
                (-0.003, 0.0, 0.004),
                (-0.02, -0.01, 0.0),
            ):
                yield {
                    "family": "failed_breakdown_recovery",
                    "parameters": {
                        "decision": decision,
                        "exit": exit_bar,
                        "low_ceiling": low,
                        "recovery_floor": recovery,
                        "current_ceiling": ceiling,
                        "recent_floor": recent,
                        "spy_floor": spy_floor,
                    },
                }
            for relative, recent, current_floor, spy_floor, prior_floor in itertools.product(
                (-0.003, -0.006, -0.01, -0.016, -0.024),
                (-0.003, 0.0, 0.004, 0.008),
                (-0.04, -0.025, -0.01),
                (-0.02, -0.01, 0.0),
                (-0.05, -0.025, 0.0),
            ):
                yield {
                    "family": "relative_laggard_recovery",
                    "parameters": {
                        "decision": decision,
                        "exit": exit_bar,
                        "relative_ceiling": relative,
                        "recent_floor": recent,
                        "current_floor": current_floor,
                        "spy_floor": spy_floor,
                        "prior_spy_floor": prior_floor,
                    },
                }
            if decision >= 23:
                for current_floor, relative, recent, contraction, spy_floor in itertools.product(
                    (0.004, 0.008, 0.012, 0.018, 0.026),
                    (0.0, 0.003, 0.006, 0.01),
                    (0.0, 0.003, 0.006, 0.01),
                    (0.6, 0.8, 1.0),
                    (-0.01, -0.005, 0.0),
                ):
                    yield {
                        "family": "contraction_relative_breakout",
                        "parameters": {
                            "decision": decision,
                            "exit": exit_bar,
                            "current_floor": current_floor,
                            "relative_floor": relative,
                            "recent_floor": recent,
                            "contraction_ceiling": contraction,
                            "spy_floor": spy_floor,
                        },
                    }
            for current_floor, relative, position, spy_floor, prior_floor in itertools.product(
                (0.004, 0.008, 0.012, 0.018, 0.026),
                (0.0, 0.003, 0.006, 0.01),
                (0.5, 0.65, 0.8),
                (-0.015, -0.005, 0.0),
                (-0.05, -0.02, 0.0),
            ):
                yield {
                    "family": "regime_selective_rotation",
                    "parameters": {
                        "decision": decision,
                        "exit": exit_bar,
                        "current_floor": current_floor,
                        "relative_floor": relative,
                        "range_position_floor": position,
                        "spy_floor": spy_floor,
                        "prior_spy_floor": prior_floor,
                    },
                }


def _primary_pass(observations: dict[str, dict[str, float | int]]) -> bool:
    oos = observations["development_oos_2024_2025"]
    return (
        float(oos["annualized_return"]) >= 0.50
        and float(oos["max_drawdown"]) < 0.20
        and float(oos["information_ratio"]) >= 1.0
        and all(float(observations[name]["annualized_return"]) > 0.0 for name in SEGMENTS)
    )


def _rank(observations: dict[str, dict[str, float | int]]) -> tuple[float, float, float]:
    return (
        min(float(observations[name]["annualized_return"]) for name in SEGMENTS),
        float(observations["development_oos_2024_2025"]["annualized_return"]),
        float(observations["development_oos_2024_2025"]["information_ratio"]),
    )


def _folds(
    values: np.ndarray, benchmark: np.ndarray, active: np.ndarray, mask: np.ndarray
) -> list[dict[str, float | int]]:
    positions = np.flatnonzero(mask)
    return [
        metrics(values[index], benchmark[index], active[index])
        for index in np.array_split(positions, 5)
    ]


def _start_dates(
    search: Search, values: np.ndarray, benchmark: np.ndarray, active: np.ndarray
) -> dict[str, dict[str, float | int]]:
    dates = pd.to_datetime(search.sessions.astype(str))
    output = {}
    for start in ("2022-07-01", "2023-01-01", "2024-01-01"):
        mask = np.asarray(dates >= pd.Timestamp(start)) & search.masks["development_all"]
        output[start] = metrics(values[mask], benchmark[mask], active[mask])
    return output


def _neighbors(specification: dict[str, Any]) -> Iterable[dict[str, Any]]:
    """Yield deterministic one-coordinate neighbors without using outcomes."""

    parameters = specification["parameters"]
    seen: set[str] = set()
    for name, value in parameters.items():
        if name in {"decision", "exit"}:
            alternatives = (int(value) - 6, int(value) + 6)
        else:
            numeric = float(value)
            alternatives = (
                numeric - (0.003 if numeric == 0.0 else max(abs(numeric) * 0.2, 0.001)),
                numeric + (0.003 if numeric == 0.0 else max(abs(numeric) * 0.2, 0.001)),
            )
        for alternative in alternatives:
            changed = {**parameters, name: alternative}
            if int(changed["decision"]) < 18 or int(changed["exit"]) > 77:
                continue
            if int(changed["decision"]) + 2 >= int(changed["exit"]):
                continue
            neighbor = {"family": specification["family"], "parameters": changed}
            identity = json.dumps(neighbor, sort_keys=True, separators=(",", ":"))
            if identity not in seen:
                seen.add(identity)
                yield neighbor


def _neighborhood(search: Search, specification: dict[str, Any]) -> dict[str, Any]:
    observations = []
    for neighbor in _neighbors(specification):
        try:
            result, _, _, _ = search.observations(neighbor)
        except (IndexError, ValueError):
            continue
        observations.append(
            {
                "candidate_id": _candidate_id(neighbor),
                "changed_parameters": neighbor["parameters"],
                "development_oos": result["development_oos_2024_2025"],
                "primary_pass": _primary_pass(result),
            }
        )
    pass_fraction = (
        sum(bool(item["primary_pass"]) for item in observations) / len(observations)
        if observations
        else 0.0
    )
    return {
        "neighbors": observations,
        "count": len(observations),
        "primary_pass_fraction": pass_fraction,
    }


def _adjusted_p(values: np.ndarray, trials: int) -> dict[str, float]:
    deviation = float(np.std(values, ddof=1))
    statistic = float(np.mean(values) / deviation * math.sqrt(len(values))) if deviation else 0.0
    raw = _normal_tail(statistic)
    return {
        "t_statistic": statistic,
        "raw_one_sided_p": raw,
        "bonferroni_p": min(1.0, raw * trials),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--top-per-family", type=int, default=100)
    args = parser.parse_args()
    started = time.monotonic()
    search = Search(args.root)
    heaps: dict[str, list[tuple[tuple[float, float, float], int, dict[str, Any]]]] = {}
    scanned = 0
    development_qualified = 0
    serial = 0
    for spec in search.specifications():
        scanned += 1
        family = str(spec["family"])
        search.family_trials[family] = search.family_trials.get(family, 0) + 1
        observations, _, _, active = search.observations(spec)
        if any(
            int(observations[name]["trades"]) < minimum
            for name, minimum in zip(SEGMENTS, (20, 8, 8), strict=True)
        ):
            continue
        rank = _rank(observations)
        if min(rank) <= 0.0:
            continue
        if _primary_pass(observations):
            development_qualified += 1
        record = {
            "candidate_id": _candidate_id(spec),
            "specification": spec,
            "standard": observations,
            "development_rank": list(rank),
            "development_trades": int(active[search.masks["development_all"]].sum()),
        }
        heap = heaps.setdefault(family, [])
        item = (rank, serial, record)
        serial += 1
        if len(heap) < args.top_per_family:
            heapq.heappush(heap, item)
        elif item[:2] > heap[0][:2]:
            heapq.heapreplace(heap, item)

    # Development ranking is now immutable. Only this fixed frontier receives 2026Q1.
    frontier = [item[2] for heap in heaps.values() for item in heap]
    frontier.sort(key=lambda item: tuple(item["development_rank"]), reverse=True)
    total_trials = sum(search.family_trials.values())
    pressure_pool = ThreadPoolExecutor(max_workers=2)
    for record in frontier:
        spec = record["specification"]
        standard, values, benchmark, active = search.observations(spec)
        cost_future = pressure_pool.submit(search.observations, spec, cost=STRESS_COST)
        delay_future = pressure_pool.submit(search.observations, spec, delay=1)
        cost_stress, _, _, _ = cost_future.result()
        latency_stress, _, _, _ = delay_future.result()
        diagnostic_mask = search.masks["consumed_2026q1_diagnostic"]
        diagnostic = metrics(
            values[diagnostic_mask], benchmark[diagnostic_mask], active[diagnostic_mask]
        )
        folds = _folds(values, benchmark, active, search.masks["development_all"])
        start_dates = _start_dates(search, values, benchmark, active)
        neighborhood = _neighborhood(search, spec)
        family_trials = search.family_trials[str(spec["family"])]
        multiple = _adjusted_p(values[search.masks["development_all"]], family_trials)
        record.update(
            {
                "standard": {**standard, "consumed_2026q1_diagnostic": diagnostic},
                "cost_18bp": cost_stress,
                "latency_one_bar_9bp": latency_stress,
                "development_folds": folds,
                "start_date_stress": start_dates,
                "parameter_neighborhood": neighborhood,
                "multiple_comparison_pressure": {
                    **multiple,
                    "family_trials": family_trials,
                    "total_trials": total_trials,
                },
            }
        )
        record["gates"] = {
            "standard_primary": _primary_pass(standard),
            "cost_18bp_primary": _primary_pass(cost_stress),
            "latency_one_bar_primary": _primary_pass(latency_stress),
            "four_of_five_positive_folds": sum(
                float(item["annualized_return"]) > 0.0 for item in folds
            )
            >= 4,
            "all_start_dates_positive": all(
                float(item["annualized_return"]) > 0.0 for item in start_dates.values()
            ),
            "parameter_neighborhood_70pct_primary": float(neighborhood["primary_pass_fraction"])
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
        "selection_contract": "ranked on 2022-2025 only; 2026Q1 loaded after frontier freeze and used only as consumed diagnostic veto",
        "data_contract": {
            role: {"dataset_id": value[0], "content_sha256": value[1], "symbols": list(value[2])}
            for role, value in DATASETS.items()
        },
        "sessions": {
            "start": str(search.sessions[0]),
            "end": str(search.sessions[-1]),
            "count": len(search.sessions),
        },
        "scan": {
            "total_parameter_cells": scanned,
            "family_parameter_cells": search.family_trials,
            "development_primary_hit_count_before_frontier_limit": development_qualified,
            "frontier_size": len(frontier),
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
                "simulation_observation_eligible_count": payload[
                    "simulation_observation_eligible_count"
                ],
                "best": frontier[0] if frontier else None,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
