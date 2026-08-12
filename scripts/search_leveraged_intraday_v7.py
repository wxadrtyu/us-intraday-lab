"""Add a non-overlapping opening trade to the strongest v6 two-stage portfolios."""

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
class Stream:
    identity: dict[str, Any]
    returns: np.ndarray
    benchmark: np.ndarray
    active: np.ndarray
    trades: np.ndarray
    weakest: float


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _id(value: object) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return "lev-v7-" + hashlib.sha256(canonical.encode()).hexdigest()[:16]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--entry-delay-bars", type=int, choices=(0, 1), default=0)
    parser.add_argument("--round-trip-cost", type=float, default=COST)
    parser.add_argument("--candidate-id")
    args = parser.parse_args()
    started = time.monotonic()
    v6 = json.loads(args.input.read_text(encoding="utf-8"))
    v5 = json.loads((args.input.parent / "leveraged-intraday-v5.json").read_text(encoding="utf-8"))
    pair = _load_pair(args.root, str(v5["datasets"]["pair"]), ("TQQQ", "SOXL"))
    spy = _load_pair(args.root, str(v5["datasets"]["benchmark"]), ("SPY",))
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
    rows = np.arange(len(sessions))
    daily = closes[:, -1, :] / opens[:, 0, :] - 1.0
    prior3 = np.full_like(daily, np.nan)
    prior3[3:] = closes[2:-1, -1, :] / opens[:-3, 0, :] - 1.0
    prior_spy = np.concatenate([[np.nan], spy_close[:-1, -1] / spy_open[:-1, 0] - 1.0])

    def outcome(selected: np.ndarray, entry: int, exit_bar: int) -> Stream:
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
        annuals = [
            float(metrics(values[mask], benchmark[mask], active[mask])["annualized_return"])
            for mask in masks
        ]
        return Stream({}, values, benchmark, active, active.astype(int), min(annuals))

    def selected_for(family: str, p: dict[str, Any]) -> tuple[np.ndarray, int, int]:
        decision = int(p["decision"])
        entry = decision + 1 + args.entry_delay_bars
        exit_bar = int(p["exit"])
        current = closes[:, decision, :] / opens[:, 0, :] - 1.0
        spy_current = spy_close[:, decision] / spy_open[:, 0] - 1.0
        stronger = np.argmax(current, axis=1)
        weaker = np.argmin(current, axis=1)
        if family == "morning_momentum":
            strength = current[rows, stronger]
            relative = strength - current[rows, 1 - stronger]
            eligible = (
                (strength >= float(p["floor"]))
                & (relative >= float(p["relative_floor"]))
                & (spy_current >= float(p["spy_floor"]))
            )
            return np.where(eligible, stronger, -1), entry, exit_bar
        if family == "morning_crash_rebound":
            asset = np.argmin(prior3, axis=1)
            eligible = (
                (prior3[rows, asset] <= float(p["crash"]))
                & (current[rows, asset] >= float(p["confirm"]))
                & (spy_current >= float(p["spy_floor"]))
                & (prior_spy > -0.06)
            )
            return np.where(eligible, asset, -1), entry, exit_bar
        recent = closes[:, decision, :] / closes[:, decision - 6, :] - 1.0
        if family == "afternoon_continuation":
            strength = current[rows, stronger]
            relative = strength - current[rows, 1 - stronger]
            cumulative_volume = volumes[:, : decision + 1, :].sum(axis=1)
            relative_volume = cumulative_volume / _rolling_median(cumulative_volume)
            range_high = highs[:, : decision + 1, :].max(axis=1)
            range_low = lows[:, : decision + 1, :].min(axis=1)
            range_position = (closes[:, decision, :] - range_low) / np.maximum(
                range_high - range_low, 1e-12
            )
            eligible = (
                (strength >= float(p["floor"]))
                & (recent[rows, stronger] >= float(p["recent_floor"]))
                & (relative >= float(p["relative_floor"]))
                & (relative_volume[rows, stronger] >= float(p["volume_floor"]))
                & (range_position[rows, stronger] >= 0.6)
                & (spy_current > -0.01)
            )
            return np.where(eligible, stronger, -1), entry, exit_bar
        if family == "afternoon_rebound":
            weakness = current[rows, weaker]
            eligible = (
                (weakness <= float(p["dip"]))
                & (recent[rows, weaker] >= float(p["bounce"]))
                & (spy_current <= float(p["spy_ceiling"]))
                & (prior3[rows, weaker] > -0.15)
            )
            return np.where(eligible, weaker, -1), entry, exit_bar
        raise ValueError(f"unsupported v6 family: {family}")

    base_streams: list[Stream] = []
    for record in v6["frontier"]:
        morning_spec = record["morning"]
        afternoon_spec = record["afternoon"]
        m_selected, m_entry, m_exit = selected_for(
            morning_spec["family"], morning_spec["parameters"]
        )
        a_selected, a_entry, a_exit = selected_for(
            afternoon_spec["family"], afternoon_spec["parameters"]
        )
        morning = outcome(m_selected, m_entry, m_exit)
        afternoon = outcome(a_selected, a_entry, a_exit)
        values = (1.0 + morning.returns) * (1.0 + afternoon.returns) - 1.0
        benchmark = (1.0 + morning.benchmark) * (1.0 + afternoon.benchmark) - 1.0
        annuals = [
            float(
                metrics(values[mask], benchmark[mask], (morning.active | afternoon.active)[mask])[
                    "annualized_return"
                ]
            )
            for mask in masks
        ]
        base_streams.append(
            Stream(
                {"morning": morning_spec, "afternoon": afternoon_spec},
                values,
                benchmark,
                morning.active | afternoon.active,
                morning.trades + afternoon.trades,
                min(annuals),
            )
        )

    opening: list[Stream] = []
    prior_close = np.vstack([np.full((1, 2), np.nan), closes[:-1, -1, :]])
    gap = opens[:, 0, :] / prior_close - 1.0
    for decision, exit_bar in itertools.product((2, 5, 8, 11), (12, 15, 18)):
        if exit_bar <= decision + 1:
            continue
        current = closes[:, decision, :] / opens[:, 0, :] - 1.0
        stronger = np.argmax(current, axis=1)
        strength = current[rows, stronger]
        relative = strength - current[rows, 1 - stronger]
        spy_current = spy_close[:, decision] / spy_open[:, 0] - 1.0
        gap_asset = np.argmax(gap, axis=1)
        for floor, relative_floor, spy_floor in itertools.product(
            (0.002, 0.004, 0.006, 0.01, 0.015), (0.0, 0.003, 0.006), (-0.005, 0.0, 0.002)
        ):
            selected = np.where(
                (strength >= floor) & (relative >= relative_floor) & (spy_current >= spy_floor),
                stronger,
                -1,
            )
            stream = outcome(selected, decision + 1 + args.entry_delay_bars, exit_bar)
            stream.identity = {
                "family": "opening_momentum",
                "parameters": {
                    "decision": decision,
                    "exit": exit_bar,
                    "floor": floor,
                    "relative_floor": relative_floor,
                    "spy_floor": spy_floor,
                },
            }
            if (
                stream.weakest > 0.0
                and stream.active[masks[0]].sum() >= 20
                and stream.active[masks[1]].sum() >= 8
            ):
                opening.append(stream)
        for gap_floor, confirm, spy_floor in itertools.product(
            (0.005, 0.01, 0.015, 0.02, 0.03), (-0.005, 0.0, 0.003, 0.006), (-0.01, -0.005, 0.0)
        ):
            eligible = (
                (gap[rows, gap_asset] >= gap_floor)
                & (current[rows, gap_asset] >= confirm)
                & (spy_current >= spy_floor)
            )
            stream = outcome(
                np.where(eligible, gap_asset, -1),
                decision + 1 + args.entry_delay_bars,
                exit_bar,
            )
            stream.identity = {
                "family": "gap_continuation",
                "parameters": {
                    "decision": decision,
                    "exit": exit_bar,
                    "gap_floor": gap_floor,
                    "confirm": confirm,
                    "spy_floor": spy_floor,
                },
            }
            if (
                stream.weakest > 0.0
                and stream.active[masks[0]].sum() >= 20
                and stream.active[masks[1]].sum() >= 8
            ):
                opening.append(stream)
    opening.sort(key=lambda item: item.weakest, reverse=True)
    opening = opening[:250]
    results = []
    requested_daily = None
    for first, base in itertools.product(opening, base_streams):
        values = (1.0 + first.returns) * (1.0 + base.returns) - 1.0
        benchmark = (1.0 + first.benchmark) * (1.0 + base.benchmark) - 1.0
        active = first.active | base.active
        observations = [metrics(values[mask], benchmark[mask], active[mask]) for mask in masks]
        combined = metrics(values[oos], benchmark[oos], active[oos])
        fold_values = [
            float(
                metrics(values[oos][indices], benchmark[oos][indices], active[oos][indices])[
                    "annualized_return"
                ]
            )
            for indices in np.array_split(np.arange(oos.sum()), 5)
        ]
        trades = int((first.trades[oos] + base.trades[oos]).sum())
        identity = {"opening": first.identity, **base.identity}
        candidate_id = _id(identity)
        if args.candidate_id is not None and candidate_id == args.candidate_id:
            requested_daily = {
                "sessions": [str(value) for value in sessions],
                "returns": [float(value) for value in values],
                "benchmark_returns": [float(value) for value in benchmark],
                "active": [bool(value) for value in active],
                "trades": [int(value) for value in (first.trades + base.trades)],
            }
        results.append(
            {
                "candidate_id": candidate_id,
                **identity,
                "train": observations[0],
                "2024": observations[1],
                "2025": observations[2],
                "combined_oos": {**combined, "trades": trades, "folds": fold_values},
                "weakest_segment_annualized_return": min(
                    float(item["annualized_return"]) for item in observations
                ),
            }
        )
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
        and int(item["combined_oos"]["trades"]) >= 100
        and sum(value > 0.0 for value in item["combined_oos"]["folds"]) >= 4
        and float(item["2024"]["annualized_return"]) > 0.0
        and float(item["2025"]["annualized_return"]) > 0.0
    ]
    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "cost": args.round_trip_cost,
        "entry_delay_bars": args.entry_delay_bars,
        "opening_candidates": len(opening),
        "base_candidates": len(base_streams),
        "combinations": len(results),
        "target_hits": target[:100],
        "frontier": results[:100],
        "requested_candidate": next(
            (
                item
                for item in results
                if args.candidate_id is not None and item["candidate_id"] == args.candidate_id
            ),
            None,
        ),
        "requested_daily": requested_daily,
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
