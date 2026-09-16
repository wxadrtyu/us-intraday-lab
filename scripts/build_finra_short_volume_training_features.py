"""Build the external causal FINRA short-volume training feature cache."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from us_intraday_lab.data.finra_short_volume_features import build_features


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_daily_prices(root: Path) -> pd.DataFrame:
    daily_root = root / "data/staging/alpaca_sip_1day_v2"
    paths = sorted(
        path
        for path in daily_root.glob("*.parquet")
        if "2020-12-" in path.name
        or path.name.startswith(("2021-", "2022-", "2023-"))
    )
    if not paths:
        raise ValueError("FINRA_DAILY_PRICE_PARTITIONS_MISSING")
    prices = pd.read_parquet(paths, columns=["symbol", "timestamp", "close"])
    prices["trade_date"] = prices["timestamp"].dt.tz_convert(
        "America/New_York"
    ).dt.date
    return prices.loc[:, ["trade_date", "symbol", "close"]]


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--coverage", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    coverage = pd.read_parquet(arguments.coverage)
    features = build_features(coverage, load_daily_prices(arguments.root.resolve()))
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = arguments.output.with_suffix(".tmp.parquet")
    features.to_parquet(temporary, index=False, compression="zstd")
    temporary.replace(arguments.output)
    report = {
        "status": "COMPLETE",
        "training_only": True,
        "rows": len(features),
        "unique_event_keys": int(
            features.loc[:, ["symbol", "session_date", "bar_idx"]]
            .drop_duplicates()
            .shape[0]
        ),
        "covered_rows": int(features["coverage_reason"].eq("COVERED").sum()),
        "short_ratio_z20_non_null": int(features["short_ratio_z20"].notna().sum()),
        "output_sha256": _sha256_file(arguments.output),
    }
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
