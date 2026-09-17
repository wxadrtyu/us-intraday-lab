from __future__ import annotations

import json
from datetime import date, timedelta

import pandas as pd
import pytest

from us_intraday_lab.data.cftc_positioning import (
    CONTRACTS,
    build_event_features,
    causal_available_date,
    parse_training_response,
)


def _record(contract_code: str, report_date: str) -> dict[str, str]:
    return {
        "report_date_as_yyyy_mm_dd": f"{report_date}T00:00:00.000",
        "cftc_contract_market_code": contract_code,
        "open_interest_all": "1000",
        "asset_mgr_positions_long": "400",
        "asset_mgr_positions_short": "200",
        "lev_money_positions_long": "150",
        "lev_money_positions_short": "250",
    }


def test_parser_preserves_exact_contract_date_grid() -> None:
    records = [
        _record(code, report_date)
        for report_date in ("2022-06-07", "2022-06-14")
        for code in CONTRACTS
    ]

    result = parse_training_response(json.dumps(records).encode())

    assert result.groupby("contract_code").size().to_dict() == {
        code: 2 for code in CONTRACTS
    }
    assert result["open_interest"].eq(1000.0).all()


def test_parser_rejects_duplicate_contract_report_key() -> None:
    duplicate = _record("13874+", "2022-06-07")

    with pytest.raises(ValueError, match="CFTC_POSITIONING_KEY_DUPLICATE"):
        parse_training_response(json.dumps([duplicate, duplicate]).encode())


def test_ion_report_uses_actual_publication_next_day_boundary() -> None:
    assert causal_available_date(date(2023, 2, 14)) == date(2023, 3, 9)


def test_ordinary_report_uses_eight_calendar_day_lag() -> None:
    assert causal_available_date(date(2022, 6, 7)) == date(2022, 6, 15)


def test_feature_join_uses_released_state_and_expires_after_fourteen_days() -> None:
    rows: list[dict[str, object]] = []
    first_report = date(2021, 1, 5)
    for week in range(26):
        report_date = first_report + timedelta(days=7 * week)
        for contract_index, code in enumerate(CONTRACTS):
            rows.append(
                {
                    "report_date": report_date,
                    "available_date": causal_available_date(report_date),
                    "contract_code": code,
                    "open_interest": 1000.0,
                    "asset_mgr_long": 350.0 + week * (contract_index + 1),
                    "asset_mgr_short": 200.0,
                    "lev_money_long": 180.0 + week * (contract_index + 2),
                    "lev_money_short": 240.0,
                }
            )
    positions = pd.DataFrame(rows)
    last_available = positions["available_date"].max()
    events = pd.DataFrame(
        {
            "symbol": ["AAA", "AAA", "AAA"],
            "session_date": [
                last_available,
                last_available + timedelta(days=15),
                date(2024, 1, 3),
            ],
            "bar_idx": [2, 2, 2],
        }
    )

    result = build_event_features(events, positions)

    assert len(result) == 2
    assert result["coverage_reason"].tolist() == ["COVERED", "CFTC_STATE_EXPIRED"]
    assert result.loc[0, "spx_asset_mgr_z26"] > 0
