"""Combine non-overlapping morning and afternoon leveraged-ETF trades."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from search_leveraged_intraday_v5 import COST, _cube, _load_pair, _rolling_median

from us_intraday_lab.fast_intraday_research import metrics


@dataclass(slots=True)
class StageCandidate:
    family: str
    parameters: dict[str, Any]
    returns: np.ndarray
    benchmark: np.ndarray
    active: np.ndarray
    weakest_annual: float


def _identity(family: str, parameters: dict[str, Any]) -> str:
    value = json.dumps([family, parameters], sort_keys=True, separators=(",", ":"))
    return "lev-v6-" + hashlib.sha256(value.encode()).hexdigest()[:16]


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _folds(values: np.ndarray) -> list[float]:
    output = []
    for indices in np.array_split(np.arange(len(values)), 5):
        output.append(
            float(
                metrics(values[indices], np.zeros(len(indices)), values[indices] != 0.0)[
                    "annualized_return"
                ]
            )
        )
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    started = time.monotonic()
    prior = json.loads(args.input.read_text(encoding="utf-8"))
    pair_id = str(prior["datasets"]["pair"])
    spy_id = str(prior["datasets"]["benchmark"])
    pair = _load_pair(args.root, pair_id, ("TQQQ", "SOXL"))
    spy = _load_pair(args.root, spy_id, ("SPY",))
    sessions = pd.Index(sorted(set(pair["session_date"]) & set(spy["session_date"])))
    pair = pair.loc[pair["session_date"].isin(sessions)]
    spy = spy.loc[spy["session_date"].isin(sessions)]
    symbols = ("TQQQ", "SOXL")
    opens = _cube(pair, sessions, symbols, "open")
    closes = _cube(pair, sessions, symbols, "close")
    highs = _cube(pair, sessions, symbols, "high")
    lows = _cube(pair, sessions, symbols, "low")
    volumes = _cube(pair, sessions, symbols, "volume")
    spy_open = _cube(spy, sessions, ("SPY",), "open")[:, :, 0]
    spy_close = _cube(spy, sessions, ("SPY",), "close")[:, :, 0]
    years = pd.to_datetime(sessions.astype(str)).year.to_numpy()
    masks = (years <= 2023, years == 2024, years == 2025)
    oos = years >= 2024
    daily = closes[:, -1, :] / opens[:, 0, :] - 1.0
    prior3 = np.full_like(daily, np.nan)
    prior3[3:] = closes[2:-1, -1, :] / opens[:-3, 0, :] - 1.0
    prior_spy = np.concatenate([[np.nan], (spy_close[:-1, -1] / spy_open[:-1, 0] - 1.0)])
    rows = np.arange(len(sessions))

    def outcome(
        selected: np.ndarray, entry: int, exit_bar: int
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        active = selected >= 0
        values = np.zeros(len(sessions))
        for asset in range(2):
            mask = selected == asset
            values[mask] = opens[mask, exit_bar, asset] / opens[mask, entry, asset] - 1.0 - COST
        benchmark = np.where(active, spy_open[:, exit_bar] / spy_open[:, entry] - 1.0, 0.0)
        return values, benchmark, active

    def retain(
        family: str,
        parameters: dict[str, Any],
        selected: np.ndarray,
        entry: int,
        exit_bar: int,
        bucket: list[StageCandidate],
    ) -> None:
        values, benchmark, active = outcome(selected, entry, exit_bar)
        observations = [metrics(values[mask], benchmark[mask], active[mask]) for mask in masks]
        annuals = [float(item["annualized_return"]) for item in observations]
        if (
            min(annuals[:2]) <= 0.0
            or int(active[masks[0]].sum()) < 25
            or int(active[masks[1]].sum()) < 8
        ):
            return
        if max(float(item["max_drawdown"]) for item in observations) >= 0.25:
            return
        bucket.append(StageCandidate(family, parameters, values, benchmark, active, min(annuals)))

    morning: list[StageCandidate] = []
    for decision, exit_bar in itertools.product((5, 11, 17), (24, 30, 36)):
        if exit_bar <= decision + 1:
            continue
        current = closes[:, decision, :] / opens[:, 0, :] - 1.0
        recent = closes[:, decision, :] / closes[:, max(0, decision - 6), :] - 1.0
        stronger = np.argmax(current, axis=1)
        weaker = np.argmin(current, axis=1)
        strength = current[rows, stronger]
        relative = strength - current[rows, 1 - stronger]
        weakness = current[rows, weaker]
        spy_current = spy_close[:, decision] / spy_open[:, 0] - 1.0
        for floor, relative_floor, spy_floor in itertools.product(
            (0.003, 0.006, 0.01, 0.015, 0.02, 0.025),
            (0.0, 0.003, 0.006, 0.01),
            (-0.01, -0.005, 0.0, 0.003),
        ):
            selected = np.where(
                (strength >= floor) & (relative >= relative_floor) & (spy_current >= spy_floor),
                stronger,
                -1,
            )
            retain(
                "morning_momentum",
                {
                    "decision": decision,
                    "exit": exit_bar,
                    "floor": floor,
                    "relative_floor": relative_floor,
                    "spy_floor": spy_floor,
                },
                selected,
                decision + 1,
                exit_bar,
                morning,
            )
        for crash, confirm, spy_floor in itertools.product(
            (-0.04, -0.05, -0.06, -0.075, -0.10, -0.125),
            (-0.005, 0.0, 0.003, 0.005, 0.008, 0.01),
            (-0.015, -0.01, -0.005, 0.0),
        ):
            asset = np.argmin(prior3, axis=1)
            selected = np.where(
                (prior3[rows, asset] <= crash)
                & (current[rows, asset] >= confirm)
                & (spy_current >= spy_floor)
                & (prior_spy > -0.06),
                asset,
                -1,
            )
            retain(
                "morning_crash_rebound",
                {
                    "decision": decision,
                    "exit": exit_bar,
                    "crash": crash,
                    "confirm": confirm,
                    "spy_floor": spy_floor,
                },
                selected,
                decision + 1,
                exit_bar,
                morning,
            )

    afternoon: list[StageCandidate] = []
    for decision, exit_bar in itertools.product((36, 47, 59), (60, 72, 77)):
        if exit_bar <= decision + 1:
            continue
        current = closes[:, decision, :] / opens[:, 0, :] - 1.0
        recent = closes[:, decision, :] / closes[:, decision - 6, :] - 1.0
        stronger = np.argmax(current, axis=1)
        weaker = np.argmin(current, axis=1)
        strength = current[rows, stronger]
        weakness = current[rows, weaker]
        relative = strength - current[rows, 1 - stronger]
        spy_current = spy_close[:, decision] / spy_open[:, 0] - 1.0
        cumulative_volume = volumes[:, : decision + 1, :].sum(axis=1)
        relative_volume = cumulative_volume / _rolling_median(cumulative_volume)
        range_high = highs[:, : decision + 1, :].max(axis=1)
        range_low = lows[:, : decision + 1, :].min(axis=1)
        range_position = (closes[:, decision, :] - range_low) / np.maximum(
            range_high - range_low, 1e-12
        )
        for floor, recent_floor, relative_floor, volume_floor in itertools.product(
            (0.005, 0.01, 0.015, 0.02, 0.03),
            (0.0, 0.003, 0.006),
            (0.0, 0.005, 0.01),
            (0.0, 1.0, 1.5),
        ):
            eligible = (
                (strength >= floor)
                & (recent[rows, stronger] >= recent_floor)
                & (relative >= relative_floor)
                & (relative_volume[rows, stronger] >= volume_floor)
                & (range_position[rows, stronger] >= 0.6)
                & (spy_current > -0.01)
            )
            retain(
                "afternoon_continuation",
                {
                    "decision": decision,
                    "exit": exit_bar,
                    "floor": floor,
                    "recent_floor": recent_floor,
                    "relative_floor": relative_floor,
                    "volume_floor": volume_floor,
                },
                np.where(eligible, stronger, -1),
                decision + 1,
                exit_bar,
                afternoon,
            )
        for dip, bounce, spy_ceiling in itertools.product(
            (-0.015, -0.02, -0.03, -0.04, -0.05),
            (0.0, 0.003, 0.006, 0.01),
            (0.0, 0.005, 0.01),
        ):
            eligible = (
                (weakness <= dip)
                & (recent[rows, weaker] >= bounce)
                & (spy_current <= spy_ceiling)
                & (prior3[rows, weaker] > -0.15)
            )
            retain(
                "afternoon_rebound",
                {
                    "decision": decision,
                    "exit": exit_bar,
                    "dip": dip,
                    "bounce": bounce,
                    "spy_ceiling": spy_ceiling,
                },
                np.where(eligible, weaker, -1),
                decision + 1,
                exit_bar,
                afternoon,
            )

    morning.sort(key=lambda item: item.weakest_annual, reverse=True)
    afternoon.sort(key=lambda item: item.weakest_annual, reverse=True)
    morning = morning[:200]
    afternoon = afternoon[:200]
    results: list[dict[str, Any]] = []
    for left, right in itertools.product(morning, afternoon):
        values = (1.0 + left.returns) * (1.0 + right.returns) - 1.0
        benchmark = (1.0 + left.benchmark) * (1.0 + right.benchmark) - 1.0
        active = left.active | right.active
        observations = [metrics(values[mask], benchmark[mask], active[mask]) for mask in masks]
        combined = metrics(values[oos], benchmark[oos], active[oos])
        folds = _folds(values[oos])
        trade_count = int(left.active[oos].sum() + right.active[oos].sum())
        record = {
            "candidate_id": _identity(
                "two_stage", {"morning": left.parameters, "afternoon": right.parameters}
            ),
            "family": "two_stage",
            "morning": {"family": left.family, "parameters": left.parameters},
            "afternoon": {"family": right.family, "parameters": right.parameters},
            "train": observations[0],
            "2024": observations[1],
            "2025": observations[2],
            "combined_oos": {**combined, "trades": trade_count, "folds": folds},
            "weakest_segment_annualized_return": min(
                float(item["annualized_return"]) for item in observations
            ),
        }
        results.append(record)
    results.sort(
        key=lambda item: (
            float(item["weakest_segment_annualized_return"]),
            float(item["combined_oos"]["annualized_return"]),
            float(item["combined_oos"]["information_ratio"]),
        ),
        reverse=True,
    )
    target = [
        item
        for item in results
        if float(item["combined_oos"]["annualized_return"]) >= 0.50
        and float(item["combined_oos"]["max_drawdown"]) < 0.20
        and float(item["combined_oos"]["information_ratio"]) >= 1.0
        and int(item["combined_oos"]["trades"]) >= 80
        and sum(value > 0.0 for value in item["combined_oos"]["folds"]) >= 4
        and float(item["2025"]["annualized_return"]) > 0.0
    ]
    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "cost": COST,
        "stage_candidates": {"morning": len(morning), "afternoon": len(afternoon)},
        "combinations": len(results),
        "target_hits": target[:100],
        "frontier": results[:100],
        "elapsed_seconds": time.monotonic() - started,
    }
    _write(args.output, payload)
    print(
        json.dumps(
            {
                "combinations": len(results),
                "target_hits": len(target),
                "best": results[0] if results else None,
                "elapsed_seconds": payload["elapsed_seconds"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
