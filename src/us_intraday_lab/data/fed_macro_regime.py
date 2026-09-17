"""Training-only Federal Reserve macro-series acquisition and causal features."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import date
from io import BytesIO

import numpy as np
import pandas as pd

TRAIN_START = date(2021, 1, 1)
TRAIN_END = date(2023, 12, 31)
SERIES_IDS = ("DGS2", "DGS10", "DGS30", "DFII10", "T10YIE", "DTWEXBGS")
SOURCE_URLS = {
    series: (
        f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
        "&cosd=2021-01-01&coed=2023-12-31"
    )
    for series in SERIES_IDS
}
Fetch = Callable[[str], bytes]


def parse_series_csv(series: str, body: bytes) -> pd.DataFrame:
    if series not in SOURCE_URLS:
        raise ValueError(f"FED_MACRO_SERIES_INVALID:{series}")
    frame = pd.read_csv(BytesIO(body), na_values=["."])
    if list(frame.columns) != ["observation_date", series]:
        raise ValueError(f"FED_MACRO_SCHEMA_INVALID:{series}")
    dates = pd.to_datetime(frame["observation_date"], errors="coerce")
    if dates.isna().any():
        raise ValueError(f"FED_MACRO_DATE_INVALID:{series}")
    result = pd.DataFrame({
        "source_date": dates.dt.date,
        series.lower(): pd.to_numeric(frame[series], errors="coerce"),
    })
    if result["source_date"].duplicated().any():
        raise ValueError(f"FED_MACRO_DATE_DUPLICATE:{series}")
    return result.loc[
        result["source_date"].map(lambda value: TRAIN_START <= value <= TRAIN_END)
    ].reset_index(drop=True)


def build_training_snapshot(fetch: Fetch) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    snapshot: pd.DataFrame | None = None
    manifest: list[dict[str, object]] = []
    for series, url in SOURCE_URLS.items():
        body = fetch(url)
        parsed = parse_series_csv(series, body)
        if parsed[series.lower()].notna().sum() < 700:
            raise RuntimeError(f"FED_MACRO_COVERAGE:{series}")
        snapshot = parsed if snapshot is None else snapshot.merge(
            parsed, how="outer", on="source_date", validate="one_to_one"
        )
        manifest.append({
            "series": series, "url": url,
            "source_sha256": hashlib.sha256(body).hexdigest(),
            "source_bytes": len(body), "non_null_training_rows": int(parsed[series.lower()].notna().sum()),
        })
    assert snapshot is not None
    return snapshot.sort_values("source_date").reset_index(drop=True), manifest


def _zscore(values: pd.Series) -> pd.Series:
    mean = values.rolling(20, min_periods=10).mean()
    deviation = values.rolling(20, min_periods=10).std(ddof=0).replace(0, np.nan)
    return (values - mean) / deviation


def build_event_features(events: pd.DataFrame, macro: pd.DataFrame) -> pd.DataFrame:
    required = {"symbol", "session_date", "bar_idx"}
    if missing := required.difference(events.columns):
        raise ValueError(f"FED_MACRO_EVENT_COLUMNS_MISSING:{sorted(missing)}")
    source = macro.copy()
    source["source_date"] = pd.to_datetime(source["source_date"]).dt.date
    if source["source_date"].duplicated().any():
        raise ValueError("FED_MACRO_SOURCE_DATE_DUPLICATE")
    source = source.sort_values("source_date").reset_index(drop=True)
    curve = source["dgs10"] - source["dgs2"]
    source["curve_inversion_stress_z20"] = -_zscore(curve)
    source["dgs10_change_1"] = source["dgs10"].diff()
    source["dfii10_change_1"] = source["dfii10"].diff()
    source["t10yie_change_1"] = source["t10yie"].diff()
    source["dtwexbgs_change_1"] = source["dtwexbgs"].pct_change(fill_method=None)

    result = events.copy()
    result["session_date"] = pd.to_datetime(result["session_date"]).dt.date
    result = result.loc[
        result["session_date"].map(lambda value: TRAIN_START <= value <= TRAIN_END)
    ].copy()
    if result.duplicated(["symbol", "session_date", "bar_idx"]).any():
        raise ValueError("FED_MACRO_EVENT_KEY_DUPLICATE")
    sessions = sorted(result["session_date"].unique())
    previous = {session: sessions[index - 1] if index else None for index, session in enumerate(sessions)}
    result["source_date"] = result["session_date"].map(previous)
    feature_columns = [
        "source_date", "curve_inversion_stress_z20", "dgs10_change_1",
        "dfii10_change_1", "t10yie_change_1", "dtwexbgs_change_1",
    ]
    result = result.merge(source[feature_columns], how="left", on="source_date", validate="many_to_one")
    result["coverage_reason"] = np.where(
        result[feature_columns[1:]].notna().all(axis=1), "COVERED", "FED_MACRO_FEATURE_MISSING"
    )
    return result
