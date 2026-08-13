"""Replay a selected v11 candidate under cost and execution-delay stress."""

from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from search_full_universe_intraday_v11 import SYMBOLS, _cube, _load_five_minute

from us_intraday_lab.fast_intraday_research import metrics

UNIVERSES = {
    "risk": tuple(range(1, 5)),
    "sectors": tuple(range(5, 16)),
    "all": tuple(range(1, 16)),
}


def _atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--search-result", required=True, type=Path)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    search = json.loads(args.search_result.read_text(encoding="utf-8"))
    matches = [
        item
        for group in (search.get("target_hits", []), search.get("near_target", []))
        for item in group
        if item.get("candidate_id") == args.candidate_id
    ]
    if not matches:
        raise ValueError("candidate not retained in search artifact")
    candidate = matches[0]
    sleeves = [
        (name, candidate[name])
        for name in ("opening", "morning", "midday_booster", "afternoon", "late_booster")
        if candidate.get(name) is not None
    ]

    frame = _load_five_minute(args.root)
    spy_sessions = frame.loc[(frame["symbol"] == "SPY") & (frame["bar"] == 0), "session_date"]
    sessions = pd.Index(sorted(spy_sessions.unique()))
    opens = _cube(frame, sessions, "open")
    closes = _cube(frame, sessions, "close")
    counts = _cube(frame, sessions, "minute_count")
    rows = np.arange(len(sessions))
    dates = pd.to_datetime(sessions.astype(str))
    years = dates.year.to_numpy()
    masks = {
        "train_2021_2023": years <= 2023,
        "2024": years == 2024,
        "2025": years == 2025,
        "development_oos_2024_2025": (years == 2024) | (years == 2025),
        "2026q1": (years == 2026) & (dates.month.to_numpy() <= 3),
        "2026_apr_aug": (years == 2026) & (dates.month.to_numpy() >= 4),
        "2026_all": years == 2026,
    }
    daily = closes[:, 77, :] / opens[:, 0, :] - 1.0
    prior5 = np.full_like(daily, np.nan)
    for index in range(5, len(sessions)):
        window = daily[index - 5 : index]
        valid = np.isfinite(window).all(axis=0)
        prior5[index, valid] = np.prod(1.0 + window[:, valid], axis=0) - 1.0

    def replay(cost: float, delay: int) -> dict[str, Any]:
        stage_returns: list[np.ndarray] = []
        stage_benchmarks: list[np.ndarray] = []
        stage_active: list[np.ndarray] = []
        for _, specification in sleeves:
            family = str(specification["family"])
            parameters = specification["parameters"]
            universe_name, rule = family.split("_", maxsplit=1)
            universe = UNIVERSES[universe_name]
            decision = int(parameters["decision"])
            entry = decision + 1 + delay
            exit_bar = int(parameters["exit"])
            if entry >= exit_bar:
                raise ValueError("execution delay eliminates holding interval")
            current = closes[:, decision, :] / opens[:, 0, :] - 1.0
            recent = closes[:, decision, :] / closes[:, max(0, decision - 6), :] - 1.0
            spy_current = current[:, 0]
            subset = current[:, universe]
            finite = np.isfinite(subset)
            if rule == "relative_strength":
                local = np.argmax(np.where(finite, subset, -np.inf), axis=1)
                selected = np.asarray(universe)[local]
                strength = current[rows, selected]
                eligible = (
                    np.isfinite(strength)
                    & (strength >= float(parameters["floor"]))
                    & (strength - spy_current >= float(parameters["relative_floor"]))
                    & (prior5[rows, selected] >= float(parameters["prior5_floor"]))
                    & (spy_current >= float(parameters["spy_floor"]))
                )
            elif rule == "trend_pullback":
                local = np.argmin(np.where(finite, subset, np.inf), axis=1)
                selected = np.asarray(universe)[local]
                weakness = current[rows, selected]
                eligible = (
                    np.isfinite(weakness)
                    & (weakness <= float(parameters["dip"]))
                    & (recent[rows, selected] >= float(parameters["bounce"]))
                    & (prior5[rows, selected] >= float(parameters["prior5_floor"]))
                    & (spy_current >= float(parameters["spy_floor"]))
                )
            else:
                raise ValueError(f"unsupported family: {family}")
            quality = (
                (counts[rows, 0, selected] >= 4)
                & (counts[rows, decision, selected] >= 4)
                & (counts[rows, entry, selected] >= 4)
                & (counts[rows, exit_bar, selected] >= 4)
                & (counts[:, entry, 0] >= 4)
                & (counts[:, exit_bar, 0] >= 4)
            )
            active = eligible & quality
            values = np.zeros(len(sessions))
            for asset in range(1, len(SYMBOLS)):
                mask = active & (selected == asset)
                values[mask] = opens[mask, exit_bar, asset] / opens[mask, entry, asset] - 1.0 - cost
            benchmark = np.where(active, opens[:, exit_bar, 0] / opens[:, entry, 0] - 1.0, 0.0)
            stage_returns.append(values)
            stage_benchmarks.append(benchmark)
            stage_active.append(active)
        values = np.prod(1.0 + np.vstack(stage_returns), axis=0) - 1.0
        benchmark = np.prod(1.0 + np.vstack(stage_benchmarks), axis=0) - 1.0
        active = np.logical_or.reduce(stage_active)
        logs = np.log1p(values)
        cumulative = np.concatenate([[0.0], np.cumsum(logs)])

        def trailing(lookback: int) -> np.ndarray:
            output = np.full(len(values), np.nan)
            output[lookback:] = np.expm1(cumulative[lookback:-1] - cumulative[: -(lookback + 1)])
            return output

        overlay_records: list[dict[str, Any]] = []
        for fast, slow, fast_floor, slow_floor in itertools.product(
            (5, 10, 20, 40),
            (20, 40, 60, 90),
            (-0.05, -0.025, 0.0, 0.025, 0.05),
            (-0.10, -0.05, -0.025, 0.0, 0.025, 0.05),
        ):
            if fast >= slow:
                continue
            enabled = (trailing(fast) >= fast_floor) & (trailing(slow) >= slow_floor)
            gated = np.where(enabled, values, 0.0)
            gated_active = enabled & active
            observations = {
                name: metrics(gated[mask], benchmark[mask], gated_active[mask])
                for name, mask in masks.items()
            }
            development = observations["development_oos_2024_2025"]
            current = observations["2026_all"]
            score = min(
                float(development["annualized_return"]) / 0.50,
                0.20 / max(float(development["max_drawdown"]), 1e-12),
                float(development["information_ratio"]),
                float(current["total_return"]) / 0.20,
                0.20 / max(float(current["max_drawdown"]), 1e-12),
                float(current["information_ratio"]),
            )
            overlay_records.append(
                {
                    "parameters": {
                        "fast": fast,
                        "slow": slow,
                        "fast_floor": fast_floor,
                        "slow_floor": slow_floor,
                    },
                    "target_score": score,
                    "observations": observations,
                }
            )
        overlay_records.sort(key=lambda item: float(item["target_score"]), reverse=True)
        overlay_targets = [item for item in overlay_records if float(item["target_score"]) >= 1.0]
        return {
            "round_trip_cost": cost,
            "entry_delay_bars": delay,
            "component_trades": int(np.vstack(stage_active).sum()),
            "observations": {
                name: metrics(values[mask], benchmark[mask], active[mask])
                for name, mask in masks.items()
            },
            "causal_overlay_target_count": len(overlay_targets),
            "causal_overlay_best": overlay_records[0],
        }

    scenarios = {
        name: replay(cost, delay)
        for name, cost, delay in (
            ("baseline_9bp", 0.0009, 0),
            ("cost_18bp", 0.0018, 0),
            ("delay_5min_9bp", 0.0009, 1),
            ("delay_5min_cost_18bp", 0.0018, 1),
        )
    }
    payload = {
        "schema_version": "1.0.0",
        "candidate_id": args.candidate_id,
        "selection_warning": "2026 was consumed during v11 selection and is not blind",
        "sleeves": dict(sleeves),
        "scenarios": scenarios,
    }
    _atomic(args.output, payload)
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
