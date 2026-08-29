"""Apply a frozen v1966-v2065 model to consumed recent sessions."""

from __future__ import annotations

import argparse
import json
import math
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from us_intraday_lab.v45_research_shadow import SYMBOLS

ASSETS = ("TQQQ", "SOXL")
SECTORS = SYMBOLS[5:]


def feature_row(bars: pd.DataFrame, session: date) -> tuple[np.ndarray, tuple[str, ...]]:
    frame = bars.copy()
    frame["timestamp"] = pd.to_datetime(frame.timestamp, utc=True)
    local = frame.timestamp.dt.tz_convert("America/New_York")
    frame["session"] = local.dt.date
    frame["minute"] = (local.dt.hour - 9) * 60 + local.dt.minute - 30
    frame = frame.loc[
        (frame.session == session) & frame.minute.between(0, 119) & frame.symbol.isin(SYMBOLS)
    ].copy()
    if frame.duplicated(["symbol", "minute"]).any():
        raise ValueError("DUPLICATE_MINUTES")
    frame["bar"] = frame.minute // 5
    grouped = frame.sort_values("timestamp").groupby(["symbol", "bar"])
    bucket = grouped.agg(
        open=("open", "first"),
        close=("close", "last"),
        high=("high", "max"),
        low=("low", "min"),
        volume=("volume", "sum"),
        first=("minute", "min"),
        last=("minute", "max"),
    )

    def value(symbol, bar, column):
        try:
            return float(bucket.loc[(symbol, bar), column])
        except KeyError:
            return math.nan

    current, recent, path, realized, signed, location = {}, {}, {}, {}, {}, {}
    for symbol in SYMBOLS:
        opening, close = value(symbol, 0, "open"), value(symbol, 23, "close")
        exact = value(symbol, 0, "first") == 0 and value(symbol, 23, "last") == 119
        current[symbol] = close / opening - 1 if exact and opening > 0 else math.nan
        old = value(symbol, 17, "close")
        recent[symbol] = (
            close / old - 1 if exact and value(symbol, 17, "last") == 89 and old > 0 else math.nan
        )
        bar_returns, bar_volumes = [], []
        highs, lows = [], []
        for bar in range(24):
            bar_open, bar_close = value(symbol, bar, "open"), value(symbol, bar, "close")
            bar_returns.append(bar_close / bar_open - 1 if bar_open > 0 else math.nan)
            bar_volumes.append(value(symbol, bar, "volume"))
            highs.append(value(symbol, bar, "high"))
            lows.append(value(symbol, bar, "low"))
        ret, vol = np.asarray(bar_returns), np.asarray(bar_volumes)
        finite = np.isfinite(ret)
        path[symbol] = (
            current[symbol] / np.abs(ret[finite]).sum()
            if finite.any() and np.abs(ret[finite]).sum() > 1e-8
            else math.nan
        )
        realized[symbol] = float(np.sqrt(np.sum(ret[finite] ** 2)))
        total = np.nansum(vol)
        signed[symbol] = (
            float(np.nansum(np.where(finite, np.sign(ret) * vol, 0)) / total)
            if total > 0
            else math.nan
        )
        high, low = np.nanmax(highs), np.nanmin(lows)
        location[symbol] = (close - low) / (high - low) if high > low else math.nan
    sectors = np.array([current[s] for s in SECTORS])
    cyclical = np.nanmean([current[SYMBOLS[i]] for i in (6, 7, 8, 9, 10, 15)])
    defensive = np.nanmean([current[SYMBOLS[i]] for i in (11, 13, 14)])
    leveraged_current = np.array([current[s] for s in ASSETS])
    leveraged_recent = np.array([recent[s] for s in ASSETS])
    row = np.array(
        [
            current["SPY"],
            realized["SPY"],
            np.mean(sectors > 0),
            np.nanstd(sectors),
            np.mean(np.array([current[s] for s in ("SPY", "QQQ", "IWM")]) > 0),
            cyclical - defensive,
            current["XLK"] - current["SPY"],
            np.nanmean(leveraged_current),
            np.nanmin(leveraged_current),
            np.ptp(leveraged_current),
            np.nanmean(leveraged_recent),
            np.nanmin(leveraged_recent),
            np.nanmean([path[s] for s in ASSETS]),
            np.nanmax([realized[s] for s in ASSETS]),
            np.nanmean([location[s] for s in ASSETS]),
            np.nanmean([signed[s] for s in ASSETS]),
        ]
    )
    names = (
        "spy_current",
        "spy_volatility",
        "sector_breadth",
        "sector_dispersion",
        "risk_asset_agreement",
        "cyclical_minus_defensive",
        "tech_minus_market",
        "leveraged_current_mean",
        "leveraged_current_min",
        "leveraged_current_spread",
        "leveraged_recent_mean",
        "leveraged_recent_min",
        "leveraged_path_efficiency_mean",
        "leveraged_realized_volatility_max",
        "leveraged_close_location_mean",
        "leveraged_signed_volume_imbalance_mean",
    )
    return row, names


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--candidate")
    parser.add_argument("--replay-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    campaign = json.loads(args.campaign.read_text())
    records = {r["candidate_id"]: r for r in campaign["records"]}
    candidate = records[args.candidate or campaign["ranked_candidate_ids"][0]]
    model, definition = candidate["model"], candidate["definition"]
    bars = pd.read_parquet(args.replay_dir / "final.parquet")
    observations = []
    for session in (date(2026, 8, 27), date(2026, 8, 28)):
        row, names = feature_row(bars, session)
        if "raw_factor_names" in model:
            positions = [names.index(name) for name in model["raw_factor_names"]]
            row = row[positions]
            observed = np.isfinite(row)
            valid = bool(observed.sum() >= model["minimum_observed"])
            row = np.where(observed, row, model["imputation"])
            if model.get("method") == "equal_weight_monotonic_zscore":
                score = (
                    float(np.mean((row - model["mean"]) / model["scale"] * model["directions"]))
                    if valid
                    else math.nan
                )
                row = None
            else:
                row = np.concatenate((row, (~observed)))
        elif tuple(model["factor_names"]) != names:
            raise ValueError("FACTOR_IDENTITY_MISMATCH")
        else:
            valid = bool(np.isfinite(row).all())
        if row is not None:
            score = float(
                (
                    model["intercept"]
                    + np.sum((row - model["mean"]) / model["scale"] * model["coefficients"])
                )
                if valid
                else math.nan
            )
        same_symbol = True  # both immutable replay signals select SOXL on both requested dates
        multiplier = (
            float(
                (definition["concentration_cap"] if same_symbol else 1.0)
                * (definition["bad_state_multiplier"] if score < definition["threshold"] else 1.0)
            )
            if valid
            else 0.0
        )
        replay = json.loads((args.replay_dir / f"{session}-final.json").read_text())
        scenarios = {
            name: {
                "baseline": value["v1254_raw_return"],
                "common_state_baseline": value["v1254_raw_return"] if valid else 0.0,
                "candidate": value["v1254_raw_return"] * multiplier,
            }
            for name, value in replay["scenarios"].items()
        }
        observations.append(
            {
                "session": str(session),
                "score": score if valid else None,
                "threshold": definition["threshold"],
                "valid": valid,
                "same_symbol": same_symbol,
                "multiplier": multiplier,
                "scenarios": scenarios,
            }
        )
    payload = {
        "status": "CONSUMED_DIAGNOSTIC_NOT_RANKING",
        "candidate_id": candidate["candidate_id"],
        "definition": definition,
        "observations": observations,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, allow_nan=False))
    print(json.dumps(payload))


if __name__ == "__main__":
    main()
