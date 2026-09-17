"""Causal training contract for CFTC TFF financial-futures positioning."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import date, timedelta
from urllib.parse import urlencode

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
