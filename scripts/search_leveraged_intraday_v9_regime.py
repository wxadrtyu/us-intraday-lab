"""Fast, development-selected search for complementary leveraged ETF intraday sleeves.

The 2026Q1 segment is loaded only after the development frontier is fixed.  It is
reported as a consumed diagnostic, never used to promote a candidate.
"""

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
from search_leveraged_intraday_v5 import _cube, _load_pair

from us_intraday_lab.fast_intraday_research import metrics


@dataclass(slots=True)
class Sleeve:
    identity: dict[str, Any]
    returns: np.ndarray
    benchmark: np.ndarray
    active: np.ndarray
    score: float


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _identity(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return "lev-v9-" + hashlib.sha256(encoded.encode()).hexdigest()[:16]


def _combine_frames(first: pd.DataFrame, second: pd.DataFrame) -> pd.DataFrame:
    return (
        pd.concat([first, second], ignore_index=True)
        .drop_duplicates(["session_date", "timestamp", "symbol"], keep="last")
        .sort_values(["session_date", "timestamp", "symbol"], kind="stable")
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--proposal", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--round-trip-cost", type=float, default=0.0009)
    parser.add_argument("--entry-delay-bars", type=int, choices=(0, 1), default=0)
    parser.add_argument("--top-per-slot", type=int, default=40)
    args = parser.parse_args()
    started = time.monotonic()
    proposal = json.loads(args.proposal.read_text(encoding="utf-8"))
    development = proposal["development_data"]
    final = proposal["sealed_final_data"]
    pair = _combine_frames(
        _load_pair(args.root, development["pair_dataset_id"], ("TQQQ", "SOXL")),
        _load_pair(args.root, final["pair_dataset_id"], ("TQQQ", "SOXL")),
    )
    spy = _combine_frames(
        _load_pair(args.root, development["benchmark_dataset_id"], ("SPY",)),
        _load_pair(args.root, final["benchmark_dataset_id"], ("SPY",)),
    )
    sessions = pd.Index(sorted(set(pair["session_date"]) & set(spy["session_date"])))
    pair = pair.loc[pair["session_date"].isin(sessions)]
    spy = spy.loc[spy["session_date"].isin(sessions)]
    opens = _cube(pair, sessions, ("TQQQ", "SOXL"), "open")
    closes = _cube(pair, sessions, ("TQQQ", "SOXL"), "close")
    spy_open = _cube(spy, sessions, ("SPY",), "open")[:, :, 0]
    spy_close = _cube(spy, sessions, ("SPY",), "close")[:, :, 0]
    rows = np.arange(len(sessions))
    dates = pd.to_datetime(sessions.astype(str))
    years = dates.year.to_numpy()
    masks = (years <= 2023, years == 2024, years == 2025)
    diagnostic = years == 2026
    development_mask = years <= 2025
    prior_close = np.vstack([np.full((1, 2), np.nan), closes[:-1, -1, :]])
    gap = opens[:, 0, :] / prior_close - 1.0
    prior_day = np.vstack([np.full((1, 2), np.nan), closes[:-1, -1, :] / opens[:-1, 0, :] - 1.0])

    def make_sleeve(
        family: str,
        parameters: dict[str, Any],
        selected: np.ndarray,
        entry: int,
        exit_bar: int,
    ) -> Sleeve | None:
        active = selected >= 0
        values = np.zeros(len(sessions))
        for asset in range(2):
            mask = selected == asset
            values[mask] = (
                opens[mask, exit_bar, asset] / opens[mask, entry, asset]
                - 1.0
                - args.round_trip_cost
            )
        benchmark = np.where(active, spy_open[:, exit_bar] / spy_open[:, entry] - 1.0, 0.0)
        observations = [metrics(values[mask], benchmark[mask], active[mask]) for mask in masks]
        if any(
            int(item["trades"]) < minimum
            for item, minimum in zip(observations, (20, 8, 8), strict=True)
        ):
            return None
        annuals = [float(item["annualized_return"]) for item in observations]
        if min(annuals) <= 0.0:
            return None
        return Sleeve(
            {"family": family, "parameters": parameters},
            values,
            benchmark,
            active,
            min(annuals),
        )

    slots = (
        ("opening", (2, 5, 8), (12, 15, 18)),
        ("morning", (17, 23, 29), (36, 42, 47)),
        ("afternoon", (47, 53, 59), (66, 72, 77)),
    )
    shortlisted: dict[str, list[Sleeve]] = {}
    scanned_sleeves = 0
    for slot, decisions, exits in slots:
        candidates: list[Sleeve] = []
        for decision, exit_bar in itertools.product(decisions, exits):
            if exit_bar <= decision + 1:
                continue
            entry = decision + 1 + args.entry_delay_bars
            current = closes[:, decision, :] / opens[:, 0, :] - 1.0
            recent = closes[:, decision, :] / closes[:, max(0, decision - 6), :] - 1.0
            spy_current = spy_close[:, decision] / spy_open[:, 0] - 1.0
            stronger = np.argmax(current, axis=1)
            weaker = np.argmin(current, axis=1)
            strength = current[rows, stronger]
            weakness = current[rows, weaker]
            relative = strength - weakness
            for floor, relative_floor, spy_floor in itertools.product(
                (0.003, 0.006, 0.01, 0.015, 0.02, 0.03),
                (0.0, 0.003, 0.006, 0.01),
                (-0.015, -0.005, 0.0, 0.003),
            ):
                scanned_sleeves += 1
                selected = np.where(
                    (strength >= floor) & (relative >= relative_floor) & (spy_current >= spy_floor),
                    stronger,
                    -1,
                )
                item = make_sleeve(
                    "cross_asset_momentum",
                    {
                        "decision": decision,
                        "exit": exit_bar,
                        "floor": floor,
                        "relative_floor": relative_floor,
                        "spy_floor": spy_floor,
                    },
                    selected,
                    entry,
                    exit_bar,
                )
                if item is not None:
                    candidates.append(item)
            for dip, bounce, spy_ceiling in itertools.product(
                (-0.006, -0.01, -0.015, -0.02, -0.03, -0.04),
                (-0.003, 0.0, 0.003, 0.006, 0.01),
                (-0.005, 0.0, 0.005, 0.015),
            ):
                scanned_sleeves += 1
                selected = np.where(
                    (weakness <= dip)
                    & (recent[rows, weaker] >= bounce)
                    & (spy_current <= spy_ceiling),
                    weaker,
                    -1,
                )
                item = make_sleeve(
                    "intraday_rebound",
                    {
                        "decision": decision,
                        "exit": exit_bar,
                        "dip": dip,
                        "bounce": bounce,
                        "spy_ceiling": spy_ceiling,
                    },
                    selected,
                    entry,
                    exit_bar,
                )
                if item is not None:
                    candidates.append(item)
            for gap_floor, confirm, spy_floor in itertools.product(
                (-0.01, -0.015, -0.02, -0.03, -0.04),
                (-0.005, 0.0, 0.003, 0.006, 0.01),
                (-0.015, -0.005, 0.0),
            ):
                scanned_sleeves += 1
                asset = np.argmin(gap, axis=1)
                selected = np.where(
                    (gap[rows, asset] <= gap_floor)
                    & (current[rows, asset] >= confirm)
                    & (spy_current >= spy_floor),
                    asset,
                    -1,
                )
                item = make_sleeve(
                    "gap_down_rebound",
                    {
                        "decision": decision,
                        "exit": exit_bar,
                        "gap_floor": gap_floor,
                        "confirm": confirm,
                        "spy_floor": spy_floor,
                    },
                    selected,
                    entry,
                    exit_bar,
                )
                if item is not None:
                    candidates.append(item)
            for prior_floor, confirm, spy_floor in itertools.product(
                (-0.02, -0.03, -0.05, -0.075, -0.10),
                (-0.005, 0.0, 0.003, 0.006, 0.01),
                (-0.015, -0.005, 0.0),
            ):
                scanned_sleeves += 1
                asset = np.argmin(prior_day, axis=1)
                selected = np.where(
                    (prior_day[rows, asset] <= prior_floor)
                    & (current[rows, asset] >= confirm)
                    & (spy_current >= spy_floor),
                    asset,
                    -1,
                )
                item = make_sleeve(
                    "prior_day_rebound",
                    {
                        "decision": decision,
                        "exit": exit_bar,
                        "prior_floor": prior_floor,
                        "confirm": confirm,
                        "spy_floor": spy_floor,
                    },
                    selected,
                    entry,
                    exit_bar,
                )
                if item is not None:
                    candidates.append(item)
        candidates.sort(key=lambda item: item.score, reverse=True)
        shortlisted[slot] = candidates[: args.top_per_slot]

    records: list[dict[str, Any]] = []
    for sleeves in itertools.product(*(shortlisted[name] for name, _, _ in slots)):
        values = np.prod(1.0 + np.vstack([item.returns for item in sleeves]), axis=0) - 1.0
        benchmark = np.prod(1.0 + np.vstack([item.benchmark for item in sleeves]), axis=0) - 1.0
        active = np.logical_or.reduce([item.active for item in sleeves])
        observations = [metrics(values[mask], benchmark[mask], active[mask]) for mask in masks]
        combined = metrics(
            values[development_mask & (years >= 2024)],
            benchmark[development_mask & (years >= 2024)],
            active[development_mask & (years >= 2024)],
        )
        identity = {slot[0]: sleeve.identity for slot, sleeve in zip(slots, sleeves, strict=True)}
        records.append(
            {
                "candidate_id": _identity(identity),
                **identity,
                "train": observations[0],
                "2024": observations[1],
                "2025": observations[2],
                "combined_development_oos": combined,
                "weakest_development_annualized_return": min(
                    float(item["annualized_return"]) for item in observations
                ),
                "consumed_2026q1_diagnostic": metrics(
                    values[diagnostic], benchmark[diagnostic], active[diagnostic]
                ),
            }
        )
    records.sort(
        key=lambda item: (
            float(item["weakest_development_annualized_return"]),
            float(item["combined_development_oos"]["annualized_return"]),
            float(item["combined_development_oos"]["information_ratio"]),
        ),
        reverse=True,
    )
    frontier = records[:100]
    target = [
        item
        for item in frontier
        if float(item["combined_development_oos"]["annualized_return"]) >= 0.50
        and float(item["combined_development_oos"]["max_drawdown"]) < 0.20
        and float(item["combined_development_oos"]["information_ratio"]) >= 1.0
        and float(item["train"]["annualized_return"]) > 0.0
        and float(item["train"]["max_drawdown"]) < 0.20
        and float(item["2024"]["annualized_return"]) > 0.0
        and float(item["2024"]["max_drawdown"]) < 0.20
        and float(item["2025"]["annualized_return"]) > 0.0
        and float(item["2025"]["max_drawdown"]) < 0.20
    ]
    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "selection_contract": "2022-2025 only; 2026Q1 is a consumed diagnostic",
        "cost": args.round_trip_cost,
        "entry_delay_bars": args.entry_delay_bars,
        "sessions": {"start": str(sessions[0]), "end": str(sessions[-1]), "count": len(sessions)},
        "scanned_sleeves": scanned_sleeves,
        "shortlisted_per_slot": {name: len(items) for name, items in shortlisted.items()},
        "portfolio_combinations": len(records),
        "development_target_hit_count": len(target),
        "development_target_hits": target,
        "frontier": frontier,
        "elapsed_seconds": time.monotonic() - started,
    }
    _write(args.output, payload)
    print(
        json.dumps(
            {
                key: payload[key]
                for key in (
                    "scanned_sleeves",
                    "portfolio_combinations",
                    "development_target_hit_count",
                    "elapsed_seconds",
                )
            },
            sort_keys=True,
        )
    )
    if frontier:
        print(json.dumps(frontier[0], sort_keys=True))


if __name__ == "__main__":
    main()
