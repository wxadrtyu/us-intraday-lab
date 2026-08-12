"""Fast checkpointed search for causal long-only TQQQ/SOXL intraday strategies."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import time
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

from us_intraday_lab.fast_intraday_research import metrics

COST = 0.0009
TARGET_ANNUAL = 0.50
TARGET_MDD = 0.20
TARGET_IR = 1.0


def _load_pair(root: Path, dataset_id: str, symbols: tuple[str, ...]) -> pd.DataFrame:
    pattern = (
        root
        / "data"
        / "lake"
        / "long_horizon"
        / "canonical"
        / dataset_id
        / "sessions"
        / "*.parquet"
    ).as_posix()
    quoted = ",".join(f"'{symbol}'" for symbol in symbols)
    frame = (
        duckdb.connect()
        .execute(
            f"""
        SELECT symbol, session_date, timestamp, open, high, low, close, volume
        FROM read_parquet(?) WHERE symbol IN ({quoted})
        ORDER BY session_date, timestamp, symbol
        """,
            [pattern],
        )
        .fetch_df()
    )
    counts = frame.groupby(["session_date", "symbol"], observed=True).size().unstack()
    good = counts.index[(counts.reindex(columns=symbols) == 78).all(axis=1)]
    return frame.loc[frame["session_date"].isin(good)].copy()


def _cube(
    frame: pd.DataFrame, sessions: pd.Index, symbols: tuple[str, ...], column: str
) -> np.ndarray:
    ordered = frame.sort_values(["session_date", "timestamp", "symbol"], kind="stable")
    ordered["bar"] = ordered.groupby(["session_date", "symbol"], observed=True).cumcount()
    wide = ordered.pivot(index=["session_date", "bar"], columns="symbol", values=column)
    wide = wide.reindex(pd.MultiIndex.from_product([sessions, range(78)]), columns=symbols)
    return wide.to_numpy(dtype=float).reshape(len(sessions), 78, len(symbols))


def _rolling_median(values: np.ndarray, lookback: int = 20, minimum: int = 10) -> np.ndarray:
    result = np.full_like(values, np.nan, dtype=float)
    for index in range(minimum, len(values)):
        result[index] = np.nanmedian(values[max(0, index - lookback) : index], axis=0)
    return result


def _segment_metrics(
    returns: np.ndarray, benchmark: np.ndarray, active: np.ndarray, mask: np.ndarray
) -> dict[str, float | int]:
    return metrics(returns[mask], benchmark[mask], active[mask])


def _fold_annuals(returns: np.ndarray, benchmark: np.ndarray, active: np.ndarray) -> list[float]:
    folds = []
    for indices in np.array_split(np.arange(len(returns)), 5):
        folds.append(
            float(
                metrics(returns[indices], benchmark[indices], active[indices])["annualized_return"]
            )
        )
    return folds


def _candidate_id(family: str, parameters: dict[str, Any]) -> str:
    canonical = json.dumps([family, parameters], sort_keys=True, separators=(",", ":"))
    return "lev-v5-" + hashlib.sha256(canonical.encode()).hexdigest()[:16]


def _write_checkpoint(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    started = time.monotonic()
    pair_id = "hf-finnhub-5min-138ddc27bc3de530051d01e30087e449"
    pair = _load_pair(args.root, pair_id, ("TQQQ", "SOXL"))
    # The SPY/TQQQ dataset is identified from its snapshot metadata rather than a mutable alias.
    candidates = sorted(
        (args.root / "data" / "lake" / "long_horizon" / "canonical").glob("hf-finnhub-5min-*")
    )
    spy_frame = None
    spy_dataset_id = None
    for candidate in candidates:
        try:
            sample = next((candidate / "sessions").glob("*.parquet"))
            symbols = set(pd.read_parquet(sample, columns=["symbol"])["symbol"])
        except (StopIteration, OSError):
            continue
        if {"SPY", "TQQQ"}.issubset(symbols):
            spy_dataset_id = candidate.name
            spy_frame = _load_pair(args.root, candidate.name, ("SPY",))
            break
    if spy_frame is None or spy_dataset_id is None:
        raise RuntimeError("no immutable SPY/TQQQ five-minute dataset was found")
    sessions = pd.Index(sorted(set(pair["session_date"]) & set(spy_frame["session_date"])))
    pair = pair.loc[pair["session_date"].isin(sessions)]
    spy_frame = spy_frame.loc[spy_frame["session_date"].isin(sessions)]
    symbols = ("TQQQ", "SOXL")
    opens = _cube(pair, sessions, symbols, "open")
    closes = _cube(pair, sessions, symbols, "close")
    highs = _cube(pair, sessions, symbols, "high")
    lows = _cube(pair, sessions, symbols, "low")
    volumes = _cube(pair, sessions, symbols, "volume")
    spy_open = _cube(spy_frame, sessions, ("SPY",), "open")[:, :, 0]
    spy_close = _cube(spy_frame, sessions, ("SPY",), "close")[:, :, 0]
    daily = closes[:, -1, :] / opens[:, 0, :] - 1.0
    prior3 = np.full_like(daily, np.nan)
    prior3[3:] = closes[2:-1, -1, :] / opens[:-3, 0, :] - 1.0
    spy_daily = spy_close[:, -1] / spy_open[:, 0] - 1.0
    prior_spy = np.concatenate([[np.nan], spy_daily[:-1]])
    years = pd.to_datetime(sessions.astype(str)).year.to_numpy()
    masks = {"train": years <= 2023, "2024": years == 2024, "2025": years == 2025}
    oos_mask = years >= 2024
    frontiers: list[dict[str, Any]] = []
    target_hits: list[dict[str, Any]] = []
    scanned = 0

    def consider(
        family: str, parameters: dict[str, Any], selected: np.ndarray, entry: int, exit_bar: int
    ) -> None:
        nonlocal scanned
        scanned += 1
        active = selected >= 0
        asset_return = np.zeros(len(sessions), dtype=float)
        for asset in range(2):
            mask = selected == asset
            asset_return[mask] = (
                opens[mask, exit_bar, asset] / opens[mask, entry, asset] - 1.0 - COST
            )
        spy_return = spy_open[:, exit_bar] / spy_open[:, entry] - 1.0
        train = _segment_metrics(asset_return, spy_return, active, masks["train"])
        if (
            train["annualized_return"] < 0.15
            or train["max_drawdown"] >= TARGET_MDD
            or train["trades"] < 40
        ):
            return
        validation = _segment_metrics(asset_return, spy_return, active, masks["2024"])
        if (
            validation["annualized_return"] <= 0.0
            or validation["max_drawdown"] >= TARGET_MDD
            or validation["trades"] < 20
        ):
            return
        test = _segment_metrics(asset_return, spy_return, active, masks["2025"])
        combined = _segment_metrics(asset_return, spy_return, active, oos_mask)
        folds = _fold_annuals(asset_return[oos_mask], spy_return[oos_mask], active[oos_mask])
        record = {
            "candidate_id": _candidate_id(family, parameters),
            "family": family,
            "parameters": parameters,
            "train": train,
            "2024": validation,
            "2025": test,
            "combined_oos": {**combined, "folds": folds},
        }
        score = min(
            float(train["annualized_return"]),
            float(validation["annualized_return"]),
            float(test["annualized_return"]),
        )
        record["weakest_segment_annualized_return"] = score
        frontiers.append(record)
        if (
            float(combined["annualized_return"]) >= TARGET_ANNUAL
            and float(combined["max_drawdown"]) < TARGET_MDD
            and float(combined["information_ratio"]) >= TARGET_IR
            and float(test["annualized_return"]) > 0.0
            and sum(value > 0.0 for value in folds) >= 4
            and int(combined["trades"]) >= 80
        ):
            target_hits.append(record)

    for decision in (5, 11, 17, 23, 35, 47):
        entry = decision + 1
        current = closes[:, decision, :] / opens[:, 0, :] - 1.0
        recent_start = max(0, decision - 6)
        recent = closes[:, decision, :] / closes[:, recent_start, :] - 1.0
        cumulative_volume = volumes[:, : decision + 1, :].sum(axis=1)
        relative_volume = cumulative_volume / _rolling_median(cumulative_volume)
        vwap = (closes[:, : decision + 1, :] * volumes[:, : decision + 1, :]).sum(
            axis=1
        ) / np.maximum(cumulative_volume, 1.0)
        range_high = highs[:, : decision + 1, :].max(axis=1)
        range_low = lows[:, : decision + 1, :].min(axis=1)
        range_position = (closes[:, decision, :] - range_low) / np.maximum(
            range_high - range_low, 1e-12
        )
        spy_current = spy_close[:, decision] / spy_open[:, 0] - 1.0
        stronger = np.argmax(current, axis=1)
        weaker = np.argmin(current, axis=1)
        rows = np.arange(len(sessions))
        strength = current[rows, stronger]
        weakness = current[rows, weaker]
        relative = strength - current[rows, 1 - stronger]
        for exit_bar in (24, 36, 48, 60, 72, 77):
            if exit_bar <= entry:
                continue
            for floor, relative_floor, volume_floor, range_floor, spy_floor in itertools.product(
                (0.0, 0.003, 0.006, 0.01, 0.015, 0.02),
                (0.0, 0.003, 0.006, 0.01),
                (0.0, 1.0, 1.5),
                (0.5, 0.7, 0.85),
                (-0.01, 0.0, 0.003),
            ):
                eligible = (
                    (strength >= floor)
                    & (relative >= relative_floor)
                    & (relative_volume[rows, stronger] >= volume_floor)
                    & (range_position[rows, stronger] >= range_floor)
                    & (closes[rows, decision, stronger] >= vwap[rows, stronger])
                    & (spy_current >= spy_floor)
                )
                selected = np.where(eligible, stronger, -1)
                consider(
                    "cross_asset_momentum",
                    {
                        "decision": decision,
                        "exit": exit_bar,
                        "floor": floor,
                        "relative_floor": relative_floor,
                        "volume_floor": volume_floor,
                        "range_floor": range_floor,
                        "spy_floor": spy_floor,
                    },
                    selected,
                    entry,
                    exit_bar,
                )
            for dip, bounce, prior_floor, spy_ceiling in itertools.product(
                (-0.01, -0.015, -0.02, -0.03, -0.04),
                (0.0, 0.003, 0.006, 0.01),
                (-0.15, -0.10, -0.05, 0.0),
                (0.0, 0.005, 0.01),
            ):
                eligible = (
                    (weakness <= dip)
                    & (recent[rows, weaker] >= bounce)
                    & (prior3[rows, weaker] >= prior_floor)
                    & (spy_current <= spy_ceiling)
                )
                selected = np.where(eligible, weaker, -1)
                consider(
                    "oversold_rebound",
                    {
                        "decision": decision,
                        "exit": exit_bar,
                        "dip": dip,
                        "bounce": bounce,
                        "prior_floor": prior_floor,
                        "spy_ceiling": spy_ceiling,
                    },
                    selected,
                    entry,
                    exit_bar,
                )
            for prior_crash, confirm, spy_floor in itertools.product(
                (-0.05, -0.075, -0.10, -0.15),
                (-0.01, 0.0, 0.005, 0.01),
                (-0.015, -0.005, 0.0),
            ):
                crash_asset = np.argmin(prior3, axis=1)
                eligible = (
                    (prior3[rows, crash_asset] <= prior_crash)
                    & (current[rows, crash_asset] >= confirm)
                    & (spy_current >= spy_floor)
                    & (prior_spy > -0.05)
                )
                selected = np.where(eligible, crash_asset, -1)
                consider(
                    "multi_day_crash_rebound",
                    {
                        "decision": decision,
                        "exit": exit_bar,
                        "prior_crash": prior_crash,
                        "confirm": confirm,
                        "spy_floor": spy_floor,
                    },
                    selected,
                    entry,
                    exit_bar,
                )
        frontiers.sort(
            key=lambda item: (
                float(item["weakest_segment_annualized_return"]),
                float(item["combined_oos"]["annualized_return"]),
                float(item["combined_oos"]["information_ratio"]),
            ),
            reverse=True,
        )
        del frontiers[500:]
        _write_checkpoint(
            args.output,
            {
                "status": "RUNNING",
                "last_completed_decision": decision,
                "scanned": scanned,
                "target_hits": target_hits[:100],
                "frontier": frontiers[:100],
            },
        )
    frontiers.sort(
        key=lambda item: (
            float(item["weakest_segment_annualized_return"]),
            float(item["combined_oos"]["annualized_return"]),
            float(item["combined_oos"]["information_ratio"]),
        ),
        reverse=True,
    )
    target_hits.sort(
        key=lambda item: (
            float(item["combined_oos"]["annualized_return"]),
            float(item["combined_oos"]["information_ratio"]),
        ),
        reverse=True,
    )
    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "datasets": {"pair": pair_id, "benchmark": spy_dataset_id},
        "sessions": {"start": str(sessions[0]), "end": str(sessions[-1]), "count": len(sessions)},
        "cost": COST,
        "target": {
            "annualized_return": TARGET_ANNUAL,
            "maximum_drawdown": TARGET_MDD,
            "information_ratio": TARGET_IR,
        },
        "scanned": scanned,
        "target_hits": target_hits[:100],
        "frontier": frontiers[:100],
        "elapsed_seconds": time.monotonic() - started,
    }
    _write_checkpoint(args.output, payload)
    print(
        json.dumps(
            {
                "scanned": scanned,
                "target_hits": len(target_hits),
                "best": frontiers[0] if frontiers else None,
                "elapsed_seconds": payload["elapsed_seconds"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
