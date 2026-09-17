"""Causal training contract for CFTC TFF financial-futures positioning."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import date, timedelta
from urllib.parse import urlencode

import numpy as np
import pandas as pd

TRAIN_START = date(2021, 1, 1)
TRAIN_END = date(2023, 12, 31)
DATASET_ID = "gpe5-46if"
CONTRACTS = {
    "13874+": "spx",
    "20974+": "nasdaq",
    "239742": "russell",
    "1170E1": "vix",
    "043602": "treasury",
}
_FIELDS = (
    "report_date_as_yyyy_mm_dd",
    "cftc_contract_market_code",
    "open_interest_all",
    "asset_mgr_positions_long",
    "asset_mgr_positions_short",
    "lev_money_positions_long",
    "lev_money_positions_short",
)
_WHERE = (
    "report_date_as_yyyy_mm_dd between '2021-01-01T00:00:00.000' "
    "and '2023-12-31T23:59:59.999' and cftc_contract_market_code in "
    "('13874+','20974+','239742','1170E1','043602')"
)
SOURCE_URL = "https://publicreporting.cftc.gov/resource/gpe5-46if.json?" + urlencode(
    {"$limit": "1000", "$select": ",".join(_FIELDS), "$where": _WHERE}
)
Fetch = Callable[[str], bytes]
ION_PUBLICATION_DATES = {
    date(2023, 1, 31): date(2023, 2, 24),
    date(2023, 2, 7): date(2023, 3, 3),
    date(2023, 2, 14): date(2023, 3, 8),
    date(2023, 2, 21): date(2023, 3, 10),
    date(2023, 2, 28): date(2023, 3, 14),
    date(2023, 3, 7): date(2023, 3, 16),
    date(2023, 3, 14): date(2023, 3, 21),
}


def causal_available_date(report_date: date) -> date:
    """Return the conservative first calendar date a report may be consumed."""
    publication = ION_PUBLICATION_DATES.get(report_date)
    return publication + timedelta(days=1) if publication else report_date + timedelta(days=8)


def parse_training_response(body: bytes) -> pd.DataFrame:
    """Validate and normalize one exact PRE training response."""
    records = json.loads(body)
    if not isinstance(records, list) or not records:
        raise ValueError("CFTC_POSITIONING_RESPONSE_EMPTY")
    frame = pd.DataFrame.from_records(records)
    if missing := set(_FIELDS).difference(frame.columns):
        raise ValueError(f"CFTC_POSITIONING_COLUMNS_MISSING:{sorted(missing)}")
    result = pd.DataFrame(
        {
            "report_date": pd.to_datetime(
                frame["report_date_as_yyyy_mm_dd"], errors="coerce"
            ).dt.date,
            "contract_code": frame["cftc_contract_market_code"].astype(str),
            "open_interest": pd.to_numeric(frame["open_interest_all"], errors="coerce"),
            "asset_mgr_long": pd.to_numeric(
                frame["asset_mgr_positions_long"], errors="coerce"
            ),
            "asset_mgr_short": pd.to_numeric(
                frame["asset_mgr_positions_short"], errors="coerce"
            ),
            "lev_money_long": pd.to_numeric(
                frame["lev_money_positions_long"], errors="coerce"
            ),
            "lev_money_short": pd.to_numeric(
                frame["lev_money_positions_short"], errors="coerce"
            ),
        }
    )
    if result.isna().any().any() or result["open_interest"].le(0).any():
        raise ValueError("CFTC_POSITIONING_VALUE_INVALID")
    if not set(result["contract_code"]).issubset(CONTRACTS):
        raise ValueError("CFTC_POSITIONING_CONTRACT_INVALID")
    if not result["report_date"].map(
        lambda value: TRAIN_START <= value <= TRAIN_END
    ).all():
        raise ValueError("CFTC_POSITIONING_TRAINING_BOUNDARY")
    if result.duplicated(["report_date", "contract_code"]).any():
        raise ValueError("CFTC_POSITIONING_KEY_DUPLICATE")
    result["available_date"] = result["report_date"].map(causal_available_date)
    return result.sort_values(["report_date", "contract_code"]).reset_index(drop=True)


def build_training_snapshot(
    fetch: Fetch,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Fetch and freeze the exact five-contract, three-year response."""
    body = fetch(SOURCE_URL)
    snapshot = parse_training_response(body)
    counts = snapshot.groupby("contract_code", observed=True).size().to_dict()
    expected = {code: 156 for code in CONTRACTS}
    if counts != expected:
        raise RuntimeError(f"CFTC_POSITIONING_COVERAGE:{counts}")
    manifest: dict[str, object] = {
        "dataset_id": DATASET_ID,
        "url": SOURCE_URL,
        "source_sha256": hashlib.sha256(body).hexdigest(),
        "source_bytes": len(body),
        "rows": len(snapshot),
        "counts_by_contract": counts,
        "training_only": True,
    }
    return snapshot, manifest


def _rolling_zscore(values: pd.Series) -> pd.Series:
    mean = values.rolling(26, min_periods=13).mean()
    deviation = values.rolling(26, min_periods=13).std(ddof=0).replace(0, np.nan)
    return (values - mean) / deviation


def build_event_features(events: pd.DataFrame, positions: pd.DataFrame) -> pd.DataFrame:
    """Join the latest released weekly state, expiring it after 14 days."""
    event_required = {"symbol", "session_date", "bar_idx"}
    position_required = {
        "report_date",
        "available_date",
        "contract_code",
        "open_interest",
        "asset_mgr_long",
        "asset_mgr_short",
        "lev_money_long",
        "lev_money_short",
    }
    if missing := event_required.difference(events.columns):
        raise ValueError(f"CFTC_POSITIONING_EVENT_COLUMNS_MISSING:{sorted(missing)}")
    if missing := position_required.difference(positions.columns):
        raise ValueError(f"CFTC_POSITIONING_SOURCE_COLUMNS_MISSING:{sorted(missing)}")

    source = positions.copy()
    source["report_date"] = pd.to_datetime(source["report_date"]).dt.date
    source["available_date"] = pd.to_datetime(source["available_date"]).dt.date
    if source.duplicated(["report_date", "contract_code"]).any():
        raise ValueError("CFTC_POSITIONING_KEY_DUPLICATE")
    source = source.sort_values(["contract_code", "report_date"]).reset_index(drop=True)
    source["asset_net"] = (
        source["asset_mgr_long"] - source["asset_mgr_short"]
    ) / source["open_interest"]
    source["lev_net"] = (
        source["lev_money_long"] - source["lev_money_short"]
    ) / source["open_interest"]
    grouped = source.groupby("contract_code", sort=False, observed=True)
    source["asset_net_z26"] = grouped["asset_net"].transform(_rolling_zscore)
    source["lev_net_z26"] = grouped["lev_net"].transform(_rolling_zscore)
    source["divergence"] = source["asset_net"] - source["lev_net"]
    source["divergence_z26"] = grouped["divergence"].transform(_rolling_zscore)
    source["lev_change"] = grouped["lev_net"].diff()
    source["lev_change_z26"] = grouped["lev_change"].transform(_rolling_zscore)
    source["asset_change"] = grouped["asset_net"].diff()
    source["asset_change_z26"] = grouped["asset_change"].transform(_rolling_zscore)

    selections = (
        ("13874+", "asset_net_z26", "spx_asset_mgr_z26"),
        ("20974+", "lev_net_z26", "nasdaq_lev_money_z26"),
        ("239742", "divergence_z26", "russell_divergence_z26"),
        ("1170E1", "lev_change_z26", "vix_lev_money_change_z26"),
        ("043602", "asset_change_z26", "treasury_asset_mgr_change_z26"),
    )
    weekly: pd.DataFrame | None = None
    for code, source_column, output_column in selections:
        selected = source.loc[
            source["contract_code"].eq(code),
            ["report_date", "available_date", source_column],
        ].rename(columns={source_column: output_column})
        weekly = (
            selected
            if weekly is None
            else weekly.merge(
                selected,
                how="outer",
                on=["report_date", "available_date"],
                validate="one_to_one",
            )
        )
    assert weekly is not None

    result = events.copy()
    result["session_date"] = pd.to_datetime(result["session_date"]).dt.date
    result = result.loc[
        result["session_date"].map(lambda value: TRAIN_START <= value <= TRAIN_END)
    ].copy()
    if result.duplicated(["symbol", "session_date", "bar_idx"]).any():
        raise ValueError("CFTC_POSITIONING_EVENT_KEY_DUPLICATE")
    result["_event_order"] = range(len(result))
    result["_session_timestamp"] = pd.to_datetime(result["session_date"])
    weekly = weekly.sort_values("available_date").copy()
    weekly["_available_timestamp"] = pd.to_datetime(weekly["available_date"])
    result = pd.merge_asof(
        result.sort_values("_session_timestamp"),
        weekly.sort_values("_available_timestamp"),
        left_on="_session_timestamp",
        right_on="_available_timestamp",
        direction="backward",
        allow_exact_matches=True,
    )
    age_days = (result["_session_timestamp"] - result["_available_timestamp"]).dt.days
    feature_columns = [item[2] for item in selections]
    expired = age_days.gt(14)
    missing = result["available_date"].isna() | result[feature_columns].isna().any(axis=1)
    result["coverage_reason"] = np.select(
        [expired, missing],
        ["CFTC_STATE_EXPIRED", "CFTC_FEATURE_MISSING"],
        default="COVERED",
    )
    unavailable = result["coverage_reason"].ne("COVERED")
    result.loc[unavailable, feature_columns] = np.nan
    return result.sort_values("_event_order").drop(
        columns=["_event_order", "_session_timestamp", "_available_timestamp"]
    )
