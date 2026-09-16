from __future__ import annotations

from datetime import date

import pandas as pd

from us_intraday_lab.data.finra_short_volume_listing import build_listing_audit, parse_month_listing

MONTH_HTML = b"""
<h2>FINRA Consolidated NMS</h2>
<ul>
  <li><a href="https://cdn.finra.org/equity/regsho/daily/CNMSshvol20210104.txt">Monday 4th</a> (TXT 309 KB)</li>
  <li><a href="https://cdn.finra.org/equity/regsho/daily/CNMSshvol20210105.txt">Tuesday 5th</a> (TXT 303 KB) Updated</li>
</ul>
<h2>FINRA/NASDAQ TRF Chicago</h2>
<ul><li><a href="https://cdn.finra.org/equity/regsho/daily/FNSQshvol20210104.txt">Monday 4th</a></li></ul>
"""


def test_parse_month_listing_isolates_nms_and_updated_label() -> None:
    listing = parse_month_listing(MONTH_HTML)

    assert listing == {
        date(2021, 1, 4): False,
        date(2021, 1, 5): True,
    }


def test_build_listing_audit_separates_original_migration_from_update() -> None:
    manifests = pd.DataFrame(
        {
            "trade_date": ["2021-01-04", "2021-01-05", "2021-07-01"],
            "last_modified": [
                "2021-05-21T07:41:28+00:00",
                "2021-05-21T07:41:28+00:00",
                "2021-07-01T21:21:13+00:00",
            ],
        }
    )
    calls: list[tuple[int, int]] = []

    def fetch(year: int, month: int) -> bytes:
        calls.append((year, month))
        return MONTH_HTML

    audit = build_listing_audit(manifests, fetch)

    assert calls == [(2021, 1)]
    assert audit["availability_evidence"].tolist() == [
        "ORIGINAL_OFFICIAL_INDEX",
        "UPDATED_OFFICIAL_INDEX",
        "SAME_DAY_LAST_MODIFIED",
    ]
    assert audit.loc[0, "causal_available_at"] == pd.Timestamp(
        "2021-01-04T23:00:00Z"
    )
    assert audit.loc[1, "causal_available_at"] == pd.Timestamp(
        "2021-05-21T07:41:28Z"
    )
    assert audit.loc[2, "causal_available_at"] == pd.Timestamp(
        "2021-07-01T21:21:13Z"
    )
    assert audit.loc[0, "index_sha256"] == audit.loc[1, "index_sha256"]
