"""One-shot evaluation of frozen v8 on the acquired 2026 blind interval."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from us_intraday_lab.fast_intraday_research import metrics

DATASET_ID = "alpaca-iex-1min-c399960d655fe2a36dfc2e51fbcc9259"
CONTENT_SHA256 = "0b0f370cbf89650b3e11922aef7a6faf4d4402dac5cd8b1e2823024f7170612e"
SYMBOLS = ("SPY", "TQQQ", "SOXL")


def _atomic_sealed(path: Path, value: object) -> None:
    encoded = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != encoded:
            raise ValueError("sealed blind result already exists with different content")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(encoded, encoding="utf-8")
    temporary.replace(path)


def _load_bars(root: Path) -> tuple[pd.DataFrame, dict[str, object]]:
    directory = root / "data" / "lake" / "acquired" / DATASET_ID
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("dataset_id") != DATASET_ID or manifest.get("content_sha256") != CONTENT_SHA256:
        raise ValueError("blind dataset identity mismatch")
    window = manifest.get("window", {})
    if not isinstance(window, dict) or window.get("blind_test_candidate") is not True:
        raise ValueError("dataset is not the predeclared blind candidate")
    quoted = ",".join(f"'{symbol}'" for symbol in SYMBOLS)
    connection = duckdb.connect()
    try:
        frame = connection.execute(
            f"""
            SELECT symbol, session_date, timestamp, open, high, low, close, volume
            FROM read_parquet(?) WHERE symbol IN ({quoted})
            ORDER BY session_date, timestamp, symbol
            """,
            [(directory / "bars.parquet").as_posix()],
        ).fetch_df()
    finally:
        connection.close()
    return frame, manifest


def _five_minute(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    retained: list[pd.DataFrame] = []
    rejected = {"under_350_minutes": 0, "missing_required_bucket": 0}
    required = {0, 2, 3, 15, 17, 18, 36, 41, 47, 48, 72, 77}
    for (_, _), group in frame.groupby(["session_date", "symbol"], observed=True, sort=True):
        if len(group) < 350:
            rejected["under_350_minutes"] += 1
            continue
        ordered = group.sort_values("timestamp", kind="stable").copy()
        eastern = ordered["timestamp"].dt.tz_convert("America/New_York")
        session_open = eastern.dt.normalize() + pd.Timedelta(hours=9, minutes=30)
        ordered["bar"] = ((eastern - session_open).dt.total_seconds() // 300).astype(int)
        bars = ordered.groupby("bar", observed=True, sort=True).agg(
            symbol=("symbol", "first"),
            session_date=("session_date", "first"),
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            minute_count=("close", "size"),
        )
        if (
            not required.issubset(set(bars.index))
            or (bars.loc[list(required), "minute_count"] < 4).any()
        ):
            rejected["missing_required_bucket"] += 1
            continue
        retained.append(bars.reset_index())
    if not retained:
        raise ValueError("no symbol sessions passed blind execution-bar quality gates")
    output = pd.concat(retained, ignore_index=True)
    counts = output.groupby("session_date", observed=True)["symbol"].nunique()
    common = counts.index[counts == len(SYMBOLS)]
    return output.loc[output["session_date"].isin(common)].copy(), rejected


def _cube(
    frame: pd.DataFrame, sessions: pd.Index, symbols: tuple[str, ...], column: str
) -> np.ndarray:
    wide = frame.pivot(index=["session_date", "bar"], columns="symbol", values=column)
    wide = wide.reindex(pd.MultiIndex.from_product([sessions, range(78)]), columns=symbols)
    return wide.to_numpy(dtype=float).reshape(len(sessions), 78, len(symbols))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--proposal", required=True, type=Path)
    parser.add_argument("--development-daily", required=True, type=Path)
    parser.add_argument("--q1-daily", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--consume-blind", action="store_true")
    args = parser.parse_args()
    if not args.consume_blind:
        raise ValueError("blind evaluation requires explicit --consume-blind authorization")
    proposal = json.loads(args.proposal.read_text(encoding="utf-8"))
    if proposal.get("candidate_id") != "lev-v8-086cf05c6e7b4eae":
        raise ValueError("unexpected frozen v8 candidate")
    minute, manifest = _load_bars(args.root)
    bars, rejected = _five_minute(minute)
    sessions = pd.Index(sorted(bars["session_date"].unique()))
    opens = _cube(bars, sessions, SYMBOLS, "open")
    closes = _cube(bars, sessions, SYMBOLS, "close")
    highs = _cube(bars, sessions, SYMBOLS, "high")
    lows = _cube(bars, sessions, SYMBOLS, "low")
    spy_open, asset_open = opens[:, :, 0], opens[:, :, 1:]
    spy_close, asset_close = closes[:, :, 0], closes[:, :, 1:]
    rows = np.arange(len(sessions))
    ordered_minute = minute.sort_values(["symbol", "session_date", "timestamp"], kind="stable")
    daily_close = ordered_minute.groupby(["symbol", "session_date"], observed=True)["close"].last()
    prior_series = daily_close.groupby(level="symbol").shift(1)
    prior_close = np.column_stack(
        [prior_series.loc[symbol].reindex(sessions).to_numpy(dtype=float) for symbol in SYMBOLS[1:]]
    )
    gap = asset_open[:, 0, :] / prior_close - 1.0
    stages: list[tuple[np.ndarray, int, int]] = []

    decision = 2
    current = asset_close[:, decision, :] / asset_open[:, 0, :] - 1.0
    asset = np.argmax(gap, axis=1)
    eligible = (
        (gap[rows, asset] >= 0.01)
        & (current[rows, asset] >= 0.006)
        & (spy_close[:, decision] / spy_open[:, 0] - 1.0 >= 0.0)
    )
    stages.append((np.where(eligible, asset, -1), 3, 15))

    decision = 17
    current = asset_close[:, decision, :] / asset_open[:, 0, :] - 1.0
    asset = np.argmax(current, axis=1)
    strength = current[rows, asset]
    relative = strength - current[rows, 1 - asset]
    eligible = (
        (strength >= 0.02)
        & (relative >= 0.003)
        & (spy_close[:, decision] / spy_open[:, 0] - 1.0 >= -0.005)
    )
    stages.append((np.where(eligible, asset, -1), 18, 36))

    decision = 47
    current = asset_close[:, decision, :] / asset_open[:, 0, :] - 1.0
    asset = np.argmax(current, axis=1)
    strength = current[rows, asset]
    relative = strength - current[rows, 1 - asset]
    recent = asset_close[:, decision, :] / asset_close[:, decision - 6, :] - 1.0
    high = np.nanmax(highs[:, : decision + 1, 1:], axis=1)
    low = np.nanmin(lows[:, : decision + 1, 1:], axis=1)
    position = (asset_close[:, decision, :] - low) / np.maximum(high - low, 1e-12)
    eligible = (
        (strength >= 0.015)
        & (recent[rows, asset] >= 0.006)
        & (relative >= 0.0)
        & (position[rows, asset] >= 0.6)
        & (spy_close[:, decision] / spy_open[:, 0] - 1.0 >= -0.01)
    )
    stages.append((np.where(eligible, asset, -1), 48, 72))

    stage_returns: list[np.ndarray] = []
    stage_benchmarks: list[np.ndarray] = []
    stage_active: list[np.ndarray] = []
    for selected, entry, exit_bar in stages:
        active = selected >= 0
        values = np.zeros(len(sessions))
        for asset_index in range(2):
            mask = selected == asset_index
            values[mask] = (
                asset_open[mask, exit_bar, asset_index] / asset_open[mask, entry, asset_index]
                - 1.0
                - 0.0009
            )
        benchmark = np.where(active, spy_open[:, exit_bar] / spy_open[:, entry] - 1.0, 0.0)
        stage_returns.append(values)
        stage_benchmarks.append(benchmark)
        stage_active.append(active)
    raw_returns = np.prod(1.0 + np.vstack(stage_returns), axis=0) - 1.0
    raw_benchmark = np.prod(1.0 + np.vstack(stage_benchmarks), axis=0) - 1.0
    raw_active = np.logical_or.reduce(stage_active)

    development = json.loads(args.development_daily.read_text(encoding="utf-8"))["requested_daily"]
    q1 = json.loads(args.q1_daily.read_text(encoding="utf-8"))["scenarios"][
        "cost_1_5x_next_bar_open"
    ]["daily"]
    history = np.asarray(development["returns"] + q1["returns"], dtype=float)
    combined = np.concatenate([history, raw_returns])
    logs = np.log1p(combined)
    cumulative = np.concatenate([[0.0], np.cumsum(logs)])

    def trailing(lookback: int) -> np.ndarray:
        output = np.full(len(combined), np.nan)
        for index in range(lookback, len(combined)):
            output[index] = np.expm1(cumulative[index] - cumulative[index - lookback])
        return output

    enabled = (trailing(5) >= -0.05) & (trailing(20) >= -0.10)
    blind_enabled = enabled[-len(raw_returns) :]
    returns = np.where(blind_enabled, raw_returns, 0.0)
    active = blind_enabled & raw_active
    observation = metrics(returns, raw_benchmark, active)
    observation["sessions"] = len(sessions)
    observation["component_trades"] = int(np.vstack(stage_active)[:, blind_enabled].sum())
    observation["enabled_sessions"] = int(blind_enabled.sum())
    result = {
        "schema_version": "1.0.0",
        "status": "SEALED_BLIND_CONSUMED",
        "candidate_id": proposal["candidate_id"],
        "proposal_file_sha256": hashlib.sha256(args.proposal.read_bytes()).hexdigest(),
        "dataset_id": DATASET_ID,
        "dataset_content_sha256": manifest["content_sha256"],
        "available_window": manifest["window"],
        "evaluable_sessions": {
            "start": str(sessions[0]),
            "end": str(sessions[-1]),
            "count": len(sessions),
        },
        "quality_rejections": rejected,
        "observation": observation,
        "daily": {
            "sessions": [str(value) for value in sessions],
            "returns": [float(value) for value in returns],
            "active": [bool(value) for value in active],
        },
        "target_2026_total_return_above_20pct": float(observation["total_return"]) > 0.20,
    }
    _atomic_sealed(args.output, result)
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "candidate_id",
                    "evaluable_sessions",
                    "observation",
                    "target_2026_total_return_above_20pct",
                )
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
