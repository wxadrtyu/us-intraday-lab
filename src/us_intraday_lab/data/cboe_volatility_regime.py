"""Training-only Cboe volatility-index acquisition and causal features."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import date
from io import BytesIO

import numpy as np
import pandas as pd

TRAIN_START = date(2021, 1, 1)
TRAIN_END = date(2023, 12, 31)
SOURCE_URLS = {
    symbol: f"https://cdn.cboe.com/api/global/us_indices/daily_prices/{symbol}_History.csv"
    for symbol in ("VIX", "VIX9D", "VVIX", "OVX", "GVZ", "VXEEM")
}
Fetch = Callable[[str], bytes]


def parse_training_csv(symbol: str, body: bytes) -> pd.DataFrame:
    """Parse one official CSV and discard every non-training row."""
    if symbol not in SOURCE_URLS:
        raise ValueError(f"CBOE_SOURCE_INVALID:{symbol}")
    frame = pd.read_csv(BytesIO(body))
    frame.columns = [str(column).strip().upper() for column in frame.columns]
    value_column = "CLOSE" if "CLOSE" in frame else symbol
    if "DATE" not in frame or value_column not in frame:
        raise ValueError(f"CBOE_SOURCE_SCHEMA_INVALID:{symbol}")
    parsed_dates = pd.to_datetime(frame["DATE"], format="%m/%d/%Y", errors="coerce")
    if parsed_dates.isna().any():
        raise ValueError(f"CBOE_SOURCE_DATE_INVALID:{symbol}")
    result = pd.DataFrame(
        {
            "source_date": parsed_dates.dt.date,
            symbol.lower(): pd.to_numeric(frame[value_column], errors="coerce"),
        }
    )
    if result["source_date"].duplicated().any():
        raise ValueError(f"CBOE_SOURCE_DATE_DUPLICATE:{symbol}")
    result = result.loc[
        result["source_date"].map(lambda value: TRAIN_START <= value <= TRAIN_END)
    ].copy()
    if result[symbol.lower()].isna().any():
        raise ValueError(f"CBOE_SOURCE_VALUE_INVALID:{symbol}")
    return result.sort_values("source_date").reset_index(drop=True)


def build_training_snapshot(fetch: Fetch) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    """Fetch all frozen sources and return only their training subsets."""
    snapshot: pd.DataFrame | None = None
    manifest: list[dict[str, object]] = []
    for symbol, url in SOURCE_URLS.items():
        body = fetch(url)
        parsed = parse_training_csv(symbol, body)
        if len(parsed) < 700:
            raise RuntimeError(f"CBOE_SOURCE_TRAINING_COVERAGE:{symbol}:{len(parsed)}")
        snapshot = (
            parsed
            if snapshot is None
            else snapshot.merge(parsed, how="outer", on="source_date", validate="one_to_one")
        )
        manifest.append(
            {
                "symbol": symbol,
                "url": url,
                "source_sha256": hashlib.sha256(body).hexdigest(),
                "source_bytes": len(body),
                "training_rows": len(parsed),
            }
        )
    assert snapshot is not None
    if not snapshot["source_date"].map(
        lambda value: TRAIN_START <= value <= TRAIN_END
    ).all():
        raise AssertionError("CBOE_SNAPSHOT_TRAINING_BOUNDARY")
    return snapshot.sort_values("source_date").reset_index(drop=True), manifest


def _zscore(values: pd.Series) -> pd.Series:
    mean = values.rolling(20, min_periods=10).mean()
    deviation = values.rolling(20, min_periods=10).std(ddof=0).replace(0, np.nan)
    return (values - mean) / deviation


def build_event_features(events: pd.DataFrame, indices: pd.DataFrame) -> pd.DataFrame:
    """Join index states from exactly the immediately prior equity session."""
    required_events = {"symbol", "session_date", "bar_idx"}
    required_indices = {"source_date", *[symbol.lower() for symbol in SOURCE_URLS]}
    if missing := required_events.difference(events.columns):
        raise ValueError(f"CBOE_EVENT_COLUMNS_MISSING:{sorted(missing)}")
    if missing := required_indices.difference(indices.columns):
        raise ValueError(f"CBOE_INDEX_COLUMNS_MISSING:{sorted(missing)}")
    result = events.copy()
    result["session_date"] = pd.to_datetime(result["session_date"]).dt.date
    if result.duplicated(["symbol", "session_date", "bar_idx"]).any():
        raise ValueError("CBOE_EVENT_KEY_DUPLICATE")
    source = indices.copy()
    source["source_date"] = pd.to_datetime(source["source_date"]).dt.date
    if source["source_date"].duplicated().any():
        raise ValueError("CBOE_SOURCE_DATE_DUPLICATE")
    source = source.sort_values("source_date").reset_index(drop=True)
    source["vix9d_vix"] = source["vix9d"] / source["vix"].replace(0, np.nan)
    source["vix9d_vix_z20"] = _zscore(source["vix9d_vix"])
    source["vvix_z20"] = _zscore(source["vvix"])
    for prefix in ("ovx", "gvz", "vxeem"):
        ratio = source[prefix] / source["vix"].replace(0, np.nan)
        source[f"{prefix}_vix_change_1"] = ratio.pct_change(fill_method=None)

    sessions = sorted(result["session_date"].unique())
    previous = {session: sessions[index - 1] if index else None for index, session in enumerate(sessions)}
    result["source_date"] = result["session_date"].map(previous)
    feature_columns = [
        "source_date",
        "vix9d_vix_z20",
        "vvix_z20",
        "ovx_vix_change_1",
        "gvz_vix_change_1",
        "vxeem_vix_change_1",
    ]
    result = result.merge(
        source.loc[:, feature_columns], how="left", on="source_date", validate="many_to_one"
    )
    result["coverage_reason"] = np.where(
        result[feature_columns[1:]].notna().all(axis=1),
        "COVERED",
        "CBOE_FEATURE_MISSING",
    )
    return result
