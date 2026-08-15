"""Causal low-turnover full-universe v12 search.

Only 2021-2025 participates in ranking.  The consumed 2026 interval and the
separately sourced 2018-2020 history are replayed after the frontier is frozen.
"""

from __future__ import annotations

import argparse
import hashlib
import heapq
import itertools
import json
import math
import time
import warnings
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

from us_intraday_lab.fast_intraday_research import metrics

ALPACA = {
    "alpaca-iex-1min-e44ab643818a7efc0da7a09f348d1fdc": "2047911532fddc3af4a3974c65d016ebe6886db6e551036386549cfaed2cd989",
    "alpaca-iex-1min-55ea51fc2f7e7ff2e8065e4bf321b6d0": "d64fd6fb360efa2192a0e85995dcbbb37308f979707f7f89f684966f490d2186",
    "alpaca-iex-1min-b96642524b1a51aa2b9574335ca591b9": "77beb8fedcc00bc41509ca5a53f1dea7b936aa4060102847071f7720322e32e0",
    "alpaca-iex-1min-dd31d6bae8aff19bf41d956330801680": "cce66813e3beb7c85ef007f9b99a454abbcc33b78510f10f541bf6e72050c820",
    "alpaca-iex-1min-37291f29e2057075b207579edf6d244b": "210930aa0c37e281463f85fc31913cab25fbf685b473fc7b9fe1d3e00ba1f719",
    "alpaca-iex-1min-ccf623196d5fae6171b7ca5ef036d665": "b2a163eaa031f6d60a9dbb7bcdd8d73d32e08cab69be89beb9ea9ed05c89f7f2",
    "alpaca-iex-1min-c399960d655fe2a36dfc2e51fbcc9259": "0b0f370cbf89650b3e11922aef7a6faf4d4402dac5cd8b1e2823024f7170612e",
}
HISTORICAL = {
    "hf-finnhub-1min-4812684e648df8fc683ea07661eb2f9d": "9e76d55ed5363026ad82b8e85a6b1808ef298d9ac72e50c064dc8ccfeef42610",
    "hf-finnhub-1min-243092ebf76c0a362976b26ba931c5c8": "0103622247b908363426221cdbc0b4307588468faa7fea1beaf1ae4322b9266e",
}
SYMBOLS = (
    "SPY",
    "QQQ",
    "IWM",
    "TQQQ",
    "SOXL",
    "XLB",
    "XLC",
    "XLE",
    "XLF",
    "XLI",
    "XLK",
    "XLP",
    "XLRE",
    "XLU",
    "XLV",
    "XLY",
)
RISK = np.array((3, 4))
SECTORS = np.arange(5, 16)
STANDARD_COST = 0.0009
STRESS_COST = 0.0018


def _atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _identity(value: object, prefix: str = "lev-v12-") -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return prefix + hashlib.sha256(encoded.encode()).hexdigest()[:16]


def _verified_paths(root: Path, source: str) -> list[str]:
    mapping = ALPACA if source == "alpaca" else HISTORICAL
    folder = "acquired" if source == "alpaca" else "acquired_hf"
    paths = []
    for dataset_id, expected in mapping.items():
        directory = root / "data" / "lake" / folder / dataset_id
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("dataset_id") != dataset_id or manifest.get("content_sha256") != expected:
            raise ValueError(f"dataset identity mismatch: {dataset_id}")
        if source == "alpaca":
            paths.append((directory / "bars.parquet").as_posix())
        else:
            paths.append((directory / "months" / "*.parquet").as_posix())
    return paths


def _load_buckets(root: Path, source: str) -> pd.DataFrame:
    paths = _verified_paths(root, source)
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
            ), bucketed AS (
              SELECT *, floor(minute_of_session / 5)::INTEGER AS bar
              FROM minute WHERE minute_of_session BETWEEN 0 AND 389
            )
            SELECT symbol, session_date, bar,
                   first(open ORDER BY timestamp) AS open,
                   last(close ORDER BY timestamp) AS close,
                   count(*) AS minute_count,
                   min(minute_of_session) AS first_minute,
                   max(minute_of_session) AS last_minute
            FROM bucketed
            GROUP BY symbol, session_date, bar
            ORDER BY session_date, bar, symbol
            """,
            [paths],
        ).fetch_df()
    finally:
        connection.close()


def _cube(frame: pd.DataFrame, sessions: pd.Index, column: str) -> np.ndarray:
    wide = frame.pivot(index=["session_date", "bar"], columns="symbol", values=column)
    wide = wide.reindex(pd.MultiIndex.from_product([sessions, range(78)]), columns=SYMBOLS)
    return wide.to_numpy(dtype=float).reshape(len(sessions), 78, len(SYMBOLS))


@dataclass(slots=True)
class ReturnStream:
    values: np.ndarray
    benchmark: np.ndarray
    active: np.ndarray
    component_trades: np.ndarray


class ResearchCube:
    def __init__(self, root: Path, source: str, boundary_tolerance: int = 0) -> None:
        frame = _load_buckets(root, source)
        spy_sessions = frame.loc[(frame["symbol"] == "SPY") & (frame["bar"] == 0), "session_date"]
        self.sessions = pd.Index(sorted(spy_sessions.unique()))
        self.dates = pd.to_datetime(self.sessions.astype(str))
        self.opens = _cube(frame, self.sessions, "open")
        self.closes = _cube(frame, self.sessions, "close")
        self.first = _cube(frame, self.sessions, "first_minute")
        self.last = _cube(frame, self.sessions, "last_minute")
        self.rows = np.arange(len(self.sessions))
        self.source = source
        self.boundary_tolerance = boundary_tolerance
        self._feature_cache: dict[int, dict[str, np.ndarray]] = {}
        daily = self.closes[:, 77, 0] / self.opens[:, 0, 0] - 1.0
        exact_daily = (self.first[:, 0, 0] <= boundary_tolerance) & (
            self.last[:, 77, 0] >= 389 - boundary_tolerance
        )
        daily = np.where(exact_daily, daily, np.nan)
        self.prior5 = np.full(len(self.sessions), np.nan)
        for index in range(5, len(self.sessions)):
            window = daily[index - 5 : index]
            if np.isfinite(window).all():
                self.prior5[index] = np.prod(1.0 + window) - 1.0

    def masks(self) -> dict[str, np.ndarray]:
        years = self.dates.year.to_numpy()
        months = self.dates.month.to_numpy()
        if self.source == "alpaca":
            return {
                "train_2021_2023": years <= 2023,
                "2024": years == 2024,
                "2025": years == 2025,
                "development_oos_2024_2025": (years == 2024) | (years == 2025),
                "development_all": years <= 2025,
                "consumed_2026q1": (years == 2026) & (months <= 3),
                "consumed_2026_apr_aug": (years == 2026) & (months >= 4),
                "consumed_2026_all": years == 2026,
            }
        return {
            "2018q4": years == 2018,
            "2019": years == 2019,
            "2020": years == 2020,
            "historical_2018_2020": years <= 2020,
        }

    def _features(self, decision: int) -> dict[str, np.ndarray]:
        if decision in self._feature_cache:
            return self._feature_cache[decision]
        current = self.closes[:, decision, :] / self.opens[:, 0, :] - 1.0
        previous = max(0, decision - 6)
        recent = self.closes[:, decision, :] / self.closes[:, previous, :] - 1.0
        exact_current = (self.first[:, 0, :] <= self.boundary_tolerance) & (
            self.last[:, decision, :] >= decision * 5 + 4 - self.boundary_tolerance
        )
        current = np.where(exact_current, current, np.nan)
        exact_recent = (
            self.last[:, previous, :] >= previous * 5 + 4 - self.boundary_tolerance
        ) & exact_current
        recent = np.where(exact_recent, recent, np.nan)
        sector = current[:, SECTORS]
        finite = np.isfinite(sector)
        available = finite.sum(axis=1)
        breadth = np.divide(
            ((sector > 0.0) & finite).sum(axis=1),
            available,
            out=np.full(len(self.sessions), np.nan),
            where=available >= 7,
        )
        earlier = self.closes[:, previous, :] / self.opens[:, 0, :] - 1.0
        exact_earlier = (self.first[:, 0, :] <= self.boundary_tolerance) & (
            self.last[:, previous, :] >= previous * 5 + 4 - self.boundary_tolerance
        )
        earlier_sector = np.where(exact_earlier[:, SECTORS], earlier[:, SECTORS], np.nan)
        earlier_finite = np.isfinite(earlier_sector)
        earlier_available = earlier_finite.sum(axis=1)
        earlier_breadth = np.divide(
            ((earlier_sector > 0.0) & earlier_finite).sum(axis=1),
            earlier_available,
            out=np.full(len(self.sessions), np.nan),
            where=earlier_available >= 7,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            dispersion = np.nanstd(sector, axis=1)
            tech = np.nanmax(current[:, (6, 10)], axis=1) - current[:, 0]
        output = {
            "current": current,
            "recent": recent,
            "spy": current[:, 0],
            "breadth": breadth,
            "breadth_change": breadth - earlier_breadth,
            "dispersion": dispersion,
            "tech": tech,
        }
        self._feature_cache[decision] = output
        return output

    def signal(self, specification: dict[str, Any]) -> np.ndarray:
        family = specification["family"]
        p = specification["parameters"]
        feature = self._features(int(p["decision"]))
        current = feature["current"]
        risk = current[:, RISK]
        finite = np.isfinite(risk)
        stronger_local = np.argmax(np.where(finite, risk, -np.inf), axis=1)
        weaker_local = np.argmin(np.where(finite, risk, np.inf), axis=1)
        stronger = RISK[stronger_local]
        weaker = RISK[weaker_local]
        valid_pair = finite.all(axis=1)
        if family == "breadth_strength":
            selected = stronger
            eligible = (
                valid_pair
                & (current[self.rows, selected] >= float(p["risk_floor"]))
                & (current[self.rows, selected] - feature["spy"] >= float(p["relative_floor"]))
                & (feature["breadth"] >= float(p["breadth_floor"]))
                & (feature["tech"] >= float(p["tech_floor"]))
                & (feature["spy"] >= float(p["spy_floor"]))
                & (self.prior5 >= float(p["prior5_floor"]))
            )
        elif family == "dispersion_breakout":
            selected = stronger
            eligible = (
                valid_pair
                & (current[self.rows, selected] >= float(p["risk_floor"]))
                & (feature["recent"][self.rows, selected] >= float(p["recent_floor"]))
                & (current[self.rows, selected] - feature["spy"] >= float(p["relative_floor"]))
                & (feature["dispersion"] <= float(p["dispersion_ceiling"]))
                & (feature["breadth"] >= float(p["breadth_floor"]))
                & (feature["spy"] >= float(p["spy_floor"]))
            )
        elif family == "breadth_recovery_reversal":
            selected = weaker
            eligible = (
                valid_pair
                & (current[self.rows, selected] <= float(p["dip_ceiling"]))
                & (feature["recent"][self.rows, selected] >= float(p["recent_floor"]))
                & (feature["breadth_change"] >= float(p["breadth_change_floor"]))
                & (feature["breadth"] >= float(p["breadth_floor"]))
                & (feature["spy"] >= float(p["spy_floor"]))
            )
        else:
            raise ValueError(f"unsupported family: {family}")
        return np.where(eligible, selected, -1)

    def replay(
        self, specifications: list[dict[str, Any]], cost: float = STANDARD_COST, delay: int = 0
    ) -> ReturnStream:
        values_list = []
        benchmark_list = []
        active_list = []
        previous_exit = -1
        for spec in specifications:
            p = spec["parameters"]
            decision = int(p["decision"])
            entry = decision + 1 + delay
            exit_bar = int(p["exit"])
            if entry >= exit_bar or previous_exit > entry:
                raise ValueError("invalid or overlapping holding intervals")
            previous_exit = exit_bar
            selected = self.signal(spec)
            safe = np.maximum(selected, 0)
            active = selected >= 0
            exact = (
                (self.first[self.rows, entry, safe] <= entry * 5 + self.boundary_tolerance)
                & (self.first[self.rows, exit_bar, safe] <= exit_bar * 5 + self.boundary_tolerance)
                & (self.first[:, entry, 0] <= entry * 5 + self.boundary_tolerance)
                & (self.first[:, exit_bar, 0] <= exit_bar * 5 + self.boundary_tolerance)
            )
            active &= exact
            values = np.zeros(len(self.sessions))
            for asset in RISK:
                mask = active & (selected == asset)
                values[mask] = (
                    self.opens[mask, exit_bar, asset] / self.opens[mask, entry, asset] - 1.0 - cost
                )
            benchmark = np.where(
                active, self.opens[:, exit_bar, 0] / self.opens[:, entry, 0] - 1.0, 0.0
            )
            values_list.append(values)
            benchmark_list.append(benchmark)
            active_list.append(active)
        return ReturnStream(
            np.prod(1.0 + np.vstack(values_list), axis=0) - 1.0,
            np.prod(1.0 + np.vstack(benchmark_list), axis=0) - 1.0,
            np.logical_or.reduce(active_list),
            np.vstack(active_list).sum(axis=0),
        )

    def observations(
        self, specifications: list[dict[str, Any]], cost: float = STANDARD_COST, delay: int = 0
    ) -> tuple[dict[str, dict[str, float | int]], ReturnStream]:
        stream = self.replay(specifications, cost=cost, delay=delay)
        return (
            {
                name: metrics(stream.values[mask], stream.benchmark[mask], stream.active[mask])
                for name, mask in self.masks().items()
                if mask.any()
            },
            stream,
        )


def _specifications(slot: str) -> Iterable[dict[str, Any]]:
    if slot == "single":
        strength_windows = itertools.product((11, 17, 23, 29, 35, 41), (59, 66, 72, 77))
        reversal_windows = itertools.product((35, 47, 59), (66, 72, 77))
    elif slot == "morning":
        strength_windows = itertools.product((11, 17, 23), (35, 41, 47))
        reversal_windows = ()
    else:
        strength_windows = itertools.product((41, 47, 53), (66, 72, 77))
        reversal_windows = itertools.product((41, 47, 53, 59), (66, 72, 77))
    for decision, exit_bar in strength_windows:
        if exit_bar <= decision + 2:
            continue
        for risk_floor, relative, breadth, tech, spy, prior in itertools.product(
            (0.003, 0.006, 0.01, 0.016),
            (0.0, 0.003, 0.006),
            (0.45, 0.60, 0.75),
            (0.0, 0.003),
            (-0.01, -0.003, 0.0),
            (-0.05, -0.02, 0.0),
        ):
            yield {
                "family": "breadth_strength",
                "parameters": {
                    "decision": decision,
                    "exit": exit_bar,
                    "risk_floor": risk_floor,
                    "relative_floor": relative,
                    "breadth_floor": breadth,
                    "tech_floor": tech,
                    "spy_floor": spy,
                    "prior5_floor": prior,
                },
            }
        for risk_floor, recent, relative, dispersion, breadth, spy in itertools.product(
            (0.003, 0.006, 0.01, 0.016),
            (0.0, 0.003, 0.006),
            (0.0, 0.003, 0.006),
            (0.006, 0.01, 0.016),
            (0.45, 0.60, 0.75),
            (-0.01, -0.003, 0.0),
        ):
            yield {
                "family": "dispersion_breakout",
                "parameters": {
                    "decision": decision,
                    "exit": exit_bar,
                    "risk_floor": risk_floor,
                    "recent_floor": recent,
                    "relative_floor": relative,
                    "dispersion_ceiling": dispersion,
                    "breadth_floor": breadth,
                    "spy_floor": spy,
                },
            }
    for decision, exit_bar in reversal_windows:
        if exit_bar <= decision + 2:
            continue
        for dip, recent, change, breadth, spy in itertools.product(
            (-0.01, -0.016, -0.024, -0.035),
            (-0.003, 0.0, 0.004),
            (0.0, 0.10, 0.20),
            (0.35, 0.50, 0.65),
            (-0.02, -0.01, 0.0),
        ):
            yield {
                "family": "breadth_recovery_reversal",
                "parameters": {
                    "decision": decision,
                    "exit": exit_bar,
                    "dip_ceiling": dip,
                    "recent_floor": recent,
                    "breadth_change_floor": change,
                    "breadth_floor": breadth,
                    "spy_floor": spy,
                },
            }


DEVELOPMENT_NAMES = ("train_2021_2023", "2024", "2025")


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
        and all(float(observations[name]["annualized_return"]) > 0.0 for name in DEVELOPMENT_NAMES)
    )


def _shortlist(cube: ResearchCube, slot: str, top: int) -> tuple[list[dict[str, Any]], int, int]:
    rank_heaps: dict[str, list[tuple[tuple[float, float, float], int, dict[str, Any]]]] = {}
    oos_heaps: dict[str, list[tuple[float, int, dict[str, Any]]]] = {}
    primary_records: list[dict[str, Any]] = []
    scanned = 0
    hits = 0
    serial = 0
    for spec in _specifications(slot):
        scanned += 1
        observations, stream = cube.observations([spec])
        if any(
            int(observations[name]["trades"]) < minimum
            for name, minimum in zip(DEVELOPMENT_NAMES, (30, 8, 8), strict=True)
        ):
            continue
        rank = _rank(observations)
        if min(rank) <= 0.0:
            continue
        primary_pass = _primary(observations)
        if primary_pass:
            hits += 1
        record = {
            "candidate_id": _identity(spec),
            "specifications": [spec],
            "development": observations,
            "development_rank": list(rank),
            "development_active_sessions": int(
                stream.active[cube.masks()["development_all"]].sum()
            ),
            "development_component_trades": int(
                stream.component_trades[cube.masks()["development_all"]].sum()
            ),
        }
        item = (rank, serial, record)
        serial += 1
        if primary_pass:
            primary_records.append(record)
        p = spec["parameters"]
        group = f"{spec['family']}:{p['decision']}:{p['exit']}"
        rank_heap = rank_heaps.setdefault(group, [])
        if len(rank_heap) < top:
            heapq.heappush(rank_heap, item)
        elif item[:2] > rank_heap[0][:2]:
            heapq.heapreplace(rank_heap, item)
        oos_item = (
            float(observations["development_oos_2024_2025"]["annualized_return"]),
            serial,
            record,
        )
        oos_heap = oos_heaps.setdefault(group, [])
        if len(oos_heap) < top:
            heapq.heappush(oos_heap, oos_item)
        elif oos_item[:2] > oos_heap[0][:2]:
            heapq.heapreplace(oos_heap, oos_item)
    unique = {
        item[2]["candidate_id"]: item[2]
        for heap in (*rank_heaps.values(), *oos_heaps.values())
        for item in heap
    }
    unique.update({item["candidate_id"]: item for item in primary_records})
    output = list(unique.values())
    output.sort(key=lambda item: tuple(item["development_rank"]), reverse=True)
    return output, scanned, hits


def _portfolio_frontier(
    cube: ResearchCube,
    morning: list[dict[str, Any]],
    afternoon: list[dict[str, Any]],
    keep: int,
) -> tuple[list[dict[str, Any]], int, int]:
    heap: list[tuple[tuple[float, float, float], int, dict[str, Any]]] = []
    primary_records: list[dict[str, Any]] = []
    scanned = 0
    hits = 0
    serial = 0
    for first, second in itertools.product(morning, afternoon):
        specifications = [first["specifications"][0], second["specifications"][0]]
        if (
            int(specifications[0]["parameters"]["exit"])
            > int(specifications[1]["parameters"]["decision"]) + 1
        ):
            continue
        scanned += 1
        observations, stream = cube.observations(specifications)
        rank = _rank(observations)
        if _primary(observations):
            hits += 1
        record = {
            "candidate_id": _identity(specifications, "lev-v12p-"),
            "specifications": specifications,
            "development": observations,
            "development_rank": list(rank),
            "development_active_sessions": int(
                stream.active[cube.masks()["development_all"]].sum()
            ),
            "development_component_trades": int(
                stream.component_trades[cube.masks()["development_all"]].sum()
            ),
        }
        if _primary(observations):
            primary_records.append(record)
        item = (rank, serial, record)
        serial += 1
        if len(heap) < keep:
            heapq.heappush(heap, item)
        elif item[:2] > heap[0][:2]:
            heapq.heapreplace(heap, item)
    unique = {item[2]["candidate_id"]: item[2] for item in heap}
    unique.update({item["candidate_id"]: item for item in primary_records})
    output = list(unique.values())
    output.sort(key=lambda item: tuple(item["development_rank"]), reverse=True)
    return output, scanned, hits


def _neighbors(specification: dict[str, Any]) -> Iterable[dict[str, Any]]:
    p = specification["parameters"]
    for name, value in p.items():
        step = 1 if name in {"decision", "exit"} else max(abs(float(value)) * 0.20, 0.001)
        for alternative in (float(value) - step, float(value) + step):
            changed = {**p, name: int(alternative) if name in {"decision", "exit"} else alternative}
            if changed["decision"] + 2 < changed["exit"] and 0 <= changed["decision"] < 76:
                yield {"family": specification["family"], "parameters": changed}


def _neighbor_stress(cube: ResearchCube, specifications: list[dict[str, Any]]) -> dict[str, Any]:
    outcomes = []
    for index, specification in enumerate(specifications):
        for neighbor in _neighbors(specification):
            changed = list(specifications)
            changed[index] = neighbor
            try:
                observation, _ = cube.observations(changed)
            except (IndexError, ValueError):
                continue
            outcomes.append(
                {"sleeve": index, "specification": neighbor, "primary_pass": _primary(observation)}
            )
    fraction = (
        sum(bool(item["primary_pass"]) for item in outcomes) / len(outcomes) if outcomes else 0.0
    )
    return {"count": len(outcomes), "primary_pass_fraction": fraction, "outcomes": outcomes}


def _normal_tail(value: float) -> float:
    return 0.5 * math.erfc(value / math.sqrt(2.0))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--top-per-family-slot", type=int, default=6)
    parser.add_argument("--frontier-size", type=int, default=200)
    parser.add_argument("--boundary-tolerance-minutes", type=int, choices=(0, 1), default=0)
    args = parser.parse_args()
    started = time.monotonic()
    development = ResearchCube(
        args.root, "alpaca", boundary_tolerance=args.boundary_tolerance_minutes
    )
    singles, single_cells, single_hits = _shortlist(development, "single", args.top_per_family_slot)
    morning, morning_cells, _ = _shortlist(development, "morning", args.top_per_family_slot)
    afternoon, afternoon_cells, _ = _shortlist(development, "afternoon", args.top_per_family_slot)
    portfolios, portfolio_cells, portfolio_hits = _portfolio_frontier(
        development, morning, afternoon, args.frontier_size
    )
    # Freeze using development evidence only.  Diagnostics are loaded below.
    all_candidates = {item["candidate_id"]: item for item in singles + portfolios}
    ranked = sorted(
        all_candidates.values(),
        key=lambda item: tuple(item["development_rank"]),
        reverse=True,
    )
    retained = {item["candidate_id"]: item for item in ranked[: args.frontier_size]}
    retained.update(
        {
            item["candidate_id"]: item
            for item in all_candidates.values()
            if _primary(item["development"])
        }
    )
    frontier = sorted(
        retained.values(), key=lambda item: tuple(item["development_rank"]), reverse=True
    )
    historical = ResearchCube(
        args.root, "historical", boundary_tolerance=args.boundary_tolerance_minutes
    )
    masks = development.masks()
    total_trials = single_cells + morning_cells + afternoon_cells + portfolio_cells

    def pressure(specifications: list[dict[str, Any]], cost: float, delay: int) -> dict[str, Any]:
        return development.observations(specifications, cost=cost, delay=delay)[0]

    pool = ThreadPoolExecutor(max_workers=2)
    for record in frontier:
        specifications = record["specifications"]
        standard, stream = development.observations(specifications)
        cost_future = pool.submit(pressure, specifications, STRESS_COST, 0)
        delay_future = pool.submit(pressure, specifications, STANDARD_COST, 1)
        historical_observation, _ = historical.observations(specifications)
        cost_stress = cost_future.result()
        delay_stress = delay_future.result()
        positions = np.flatnonzero(masks["development_all"])
        folds = [
            metrics(stream.values[index], stream.benchmark[index], stream.active[index])
            for index in np.array_split(positions, 5)
        ]
        starts = {}
        for start in ("2022-01-01", "2023-01-01", "2024-01-01"):
            mask = np.asarray(development.dates >= pd.Timestamp(start)) & masks["development_all"]
            starts[start] = metrics(
                stream.values[mask], stream.benchmark[mask], stream.active[mask]
            )
        neighborhood = _neighbor_stress(development, specifications)
        dev_values = stream.values[masks["development_all"]]
        deviation = float(np.std(dev_values, ddof=1))
        statistic = (
            float(np.mean(dev_values) / deviation * math.sqrt(len(dev_values)))
            if deviation > 0.0
            else 0.0
        )
        bonferroni = min(1.0, _normal_tail(statistic) * total_trials)
        historical_all = historical_observation["historical_2018_2020"]
        consumed = standard["consumed_2026_all"]
        gates = {
            "standard_primary": _primary(standard),
            "cost_18bp_primary": _primary(cost_stress),
            "delay_5min_primary": _primary(delay_stress),
            "four_of_five_positive_folds": sum(
                float(item["annualized_return"]) > 0 for item in folds
            )
            >= 4,
            "parameter_neighborhood_70pct_primary": float(neighborhood["primary_pass_fraction"])
            >= 0.70,
            "multiple_comparison_bonferroni_5pct": bonferroni < 0.05,
            "historical_cross_source_positive": float(historical_all["annualized_return"]) > 0.0,
            "historical_cross_source_mdd_below_20pct": float(historical_all["max_drawdown"]) < 0.20,
            "consumed_2026_positive": float(consumed["total_return"]) > 0.0,
            "consumed_2026_mdd_below_20pct": float(consumed["max_drawdown"]) < 0.20,
            "consumed_2026_ir_at_least_1": float(consumed["information_ratio"]) >= 1.0,
        }
        record.update(
            {
                "standard": standard,
                "cost_18bp": cost_stress,
                "delay_5min_9bp": delay_stress,
                "historical_cross_source": historical_observation,
                "development_folds": folds,
                "start_date_stress": starts,
                "parameter_neighborhood": neighborhood,
                "multiple_comparison_pressure": {
                    "t_statistic": statistic,
                    "bonferroni_p": bonferroni,
                    "total_trials": total_trials,
                },
                "gates": gates,
                "eligible_for_future_simulation_observation": all(gates.values()),
            }
        )
    pool.shutdown()
    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "selection_contract": "2021-2025 only; 2018-2020 and 2026 attached after frontier freeze",
        "execution_contract": "long only, no overnight, gross <= 1, bounded minute boundaries, <=2 round trips/session",
        "boundary_tolerance_minutes": args.boundary_tolerance_minutes,
        "datasets": {"alpaca": ALPACA, "historical_cross_source": HISTORICAL},
        "scan": {
            "single_cells": single_cells,
            "morning_cells": morning_cells,
            "afternoon_cells": afternoon_cells,
            "portfolio_cells": portfolio_cells,
            "single_shortlist": len(singles),
            "morning_shortlist": len(morning),
            "afternoon_shortlist": len(afternoon),
            "total_trials": total_trials,
            "single_primary_hits": single_hits,
            "portfolio_primary_hits": portfolio_hits,
            "frontier_size": len(frontier),
            "pressure_workers": 2,
            "elapsed_seconds": time.monotonic() - started,
        },
        "eligible_count": sum(
            bool(item["eligible_for_future_simulation_observation"]) for item in frontier
        ),
        "frontier": frontier,
    }
    _atomic(args.output, payload)
    print(
        json.dumps(
            {
                "scan": payload["scan"],
                "eligible": payload["eligible_count"],
                "best": frontier[0] if frontier else None,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
