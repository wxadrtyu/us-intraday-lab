"""One-shot sealed 2026Q1 evaluation of the frozen leveraged intraday v7 strategy."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from search_leveraged_intraday_v5 import _cube, _load_pair

from us_intraday_lab.fast_intraday_research import metrics


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != encoded:
            raise ValueError("sealed final artifact already exists with different content")
        return
    temporary = path.with_suffix(".tmp")
    temporary.write_text(encoded, encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--proposal", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    proposal = json.loads(args.proposal.read_text(encoding="utf-8"))
    if proposal["lifecycle_state"] != "frozen_awaiting_sealed_final":
        raise ValueError("proposal is not frozen for sealed final evaluation")
    final = proposal["sealed_final_data"]
    for key in ("pair", "benchmark"):
        manifest = (
            args.root
            / "data"
            / "lake"
            / "long_horizon"
            / "canonical"
            / final[f"{key}_dataset_id"]
            / "manifest.json"
        )
        observed = json.loads(manifest.read_text(encoding="utf-8"))
        if observed["content_sha256"] != final[f"{key}_content_sha256"]:
            raise ValueError(f"sealed {key} dataset content identity mismatch")
    pair = _load_pair(args.root, final["pair_dataset_id"], ("TQQQ", "SOXL"))
    spy = _load_pair(args.root, final["benchmark_dataset_id"], ("SPY",))
    sessions = pd.Index(sorted(set(pair["session_date"]) & set(spy["session_date"])))
    pair = pair.loc[pair["session_date"].isin(sessions)]
    spy = spy.loc[spy["session_date"].isin(sessions)]
    symbols = ("TQQQ", "SOXL")
    opens = _cube(pair, sessions, symbols, "open")
    closes = _cube(pair, sessions, symbols, "close")
    highs = _cube(pair, sessions, symbols, "high")
    lows = _cube(pair, sessions, symbols, "low")
    spy_open = _cube(spy, sessions, ("SPY",), "open")[:, :, 0]
    spy_close = _cube(spy, sessions, ("SPY",), "close")[:, :, 0]
    rows = np.arange(len(sessions))
    prior_close = np.vstack([np.full((1, 2), np.nan), closes[:-1, -1, :]])
    gap = opens[:, 0, :] / prior_close - 1.0

    def signals() -> list[tuple[np.ndarray, int, int]]:
        output = []
        opening, morning, afternoon = proposal["windows"]
        decision = int(opening["decision_bar"])
        current = closes[:, decision, :] / opens[:, 0, :] - 1.0
        asset = np.argmax(gap, axis=1)
        spy_current = spy_close[:, decision] / spy_open[:, 0] - 1.0
        eligible = (
            (gap[rows, asset] >= float(opening["gap_floor"]))
            & (current[rows, asset] >= float(opening["confirmation_floor"]))
            & (spy_current >= float(opening["spy_current_floor"]))
        )
        output.append(
            (np.where(eligible, asset, -1), int(opening["entry_bar"]), int(opening["exit_bar"]))
        )
        for window in (morning, afternoon):
            decision = int(window["decision_bar"])
            current = closes[:, decision, :] / opens[:, 0, :] - 1.0
            asset = np.argmax(current, axis=1)
            strength = current[rows, asset]
            relative = strength - current[rows, 1 - asset]
            spy_current = spy_close[:, decision] / spy_open[:, 0] - 1.0
            eligible = (
                (strength >= float(window["current_return_floor"]))
                & (relative >= float(window["relative_return_floor"]))
                & (spy_current >= float(window["spy_current_floor"]))
            )
            if window["name"] == "afternoon_continuation":
                recent = closes[:, decision, :] / closes[:, decision - 6, :] - 1.0
                high = highs[:, : decision + 1, :].max(axis=1)
                low = lows[:, : decision + 1, :].min(axis=1)
                position = (closes[:, decision, :] - low) / np.maximum(high - low, 1e-12)
                eligible &= (
                    recent[rows, asset] >= float(window["recent_six_bar_return_floor"])
                ) & (position[rows, asset] >= float(window["minimum_opening_range_position"]))
            output.append(
                (np.where(eligible, asset, -1), int(window["entry_bar"]), int(window["exit_bar"]))
            )
        return output

    frozen_signals = signals()
    final_mask = pd.to_datetime(sessions.astype(str)).year == 2026

    def scenario(cost: float, delay: int) -> dict[str, Any]:
        stage_returns = []
        stage_benchmarks = []
        stage_active = []
        stage_observations = []
        components = np.zeros((len(sessions), 2))
        for selected, entry, exit_bar in frozen_signals:
            active = selected >= 0
            values = np.zeros(len(sessions))
            for asset in range(2):
                mask = selected == asset
                values[mask] = (
                    opens[mask, exit_bar, asset] / opens[mask, entry + delay, asset] - 1.0 - cost
                )
                components[mask, asset] += values[mask]
            benchmark = np.where(
                active, spy_open[:, exit_bar] / spy_open[:, entry + delay] - 1.0, 0.0
            )
            stage_returns.append(values)
            stage_benchmarks.append(benchmark)
            stage_active.append(active)
            stage_observations.append(
                metrics(values[final_mask], benchmark[final_mask], active[final_mask])
            )
        returns = np.prod(1.0 + np.vstack(stage_returns), axis=0) - 1.0
        benchmark = np.prod(1.0 + np.vstack(stage_benchmarks), axis=0) - 1.0
        active = np.logical_or.reduce(stage_active)
        observation = metrics(returns[final_mask], benchmark[final_mask], active[final_mask])
        observation["trades"] = int(sum(item[final_mask].sum() for item in stage_active))
        observation["sessions"] = int(final_mask.sum())
        pnl = components[final_mask].sum(axis=0).clip(min=0.0)
        observation["positive_symbol_concentration"] = (
            float(pnl.max() / pnl.sum()) if pnl.sum() > 0.0 else 1.0
        )
        observation["stages"] = {
            window["name"]: stage_observation
            for window, stage_observation in zip(
                proposal["windows"], stage_observations, strict=True
            )
        }
        observation["daily"] = {
            "sessions": [str(value) for value in sessions[final_mask]],
            "returns": [float(value) for value in returns[final_mask]],
            "benchmark_returns": [float(value) for value in benchmark[final_mask]],
            "active": [bool(value) for value in active[final_mask]],
            "trades": [int(value) for value in np.vstack(stage_active)[:, final_mask].sum(axis=0)],
        }
        return observation

    result = {
        "schema_version": "1.0.0",
        "proposal_id": proposal["proposal_id"],
        "candidate_id": proposal["candidate_id"],
        "proposal_file_sha256": _sha256(args.proposal),
        "sealed_period": "2026-01-01/2026-03-30",
        "scenarios": {
            "cost_1_5x_next_bar_open": scenario(0.0009, 0),
            "cost_2x_next_bar_open": scenario(0.0018, 0),
            "cost_1_5x_one_bar_delay": scenario(0.0009, 1),
            "cost_2x_one_bar_delay": scenario(0.0018, 1),
        },
    }
    primary = result["scenarios"]["cost_1_5x_next_bar_open"]
    targets = proposal["hard_targets"]
    result["sealed_primary_targets_passed"] = (
        float(primary["annualized_return"])
        >= float(targets["minimum_cost_adjusted_annualized_return"])
        and float(primary["max_drawdown"]) < float(targets["maximum_drawdown"])
        and float(primary["information_ratio"]) >= float(targets["minimum_information_ratio"])
    )
    _write(args.output, result)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
