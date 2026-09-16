from __future__ import annotations

from datetime import date
from http.client import RemoteDisconnected
from urllib.error import HTTPError

import pandas as pd
import pytest

from us_intraday_lab.data.finra_short_volume_acquisition import (
    HttpPayload,
    acquire_sessions,
    fetch_daily_file,
    parse_daily_file,
)


def _body(*rows: str, footer: int | None = None) -> bytes:
    count = len(rows) if footer is None else footer
    lines = [
        "Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market",
        *rows,
        str(count),
    ]
    return ("\n".join(lines) + "\n").encode()


def _payload(body: bytes, *, modified: str = "Mon, 03 Jan 2022 22:19:58 GMT") -> HttpPayload:
    return HttpPayload(
        body=body,
        status=200,
        headers={"Last-Modified": modified, "ETag": 'W/"abc"'},
        url="https://cdn.finra.org/example.txt",
    )


def test_parse_daily_file_preserves_exact_symbols_and_validates_footer() -> None:
    frame = parse_daily_file(
        _body(
            "20220103|ABC|50|2|100|B,Q,N",
            "20220103|ABpC|10|0|20|Q",
        ),
        date(2022, 1, 3),
    )

    assert frame["symbol"].tolist() == ["ABC", "ABpC"]
    assert frame["short_volume"].tolist() == [50.0, 10.0]
    assert frame.attrs["footer_count"] == 2

    with pytest.raises(ValueError, match="FINRA_FOOTER_COUNT_MISMATCH"):
        parse_daily_file(
            _body("20220103|ABC|50|2|100|Q", footer=2), date(2022, 1, 3)
        )


@pytest.mark.parametrize(
    ("rows", "reason"),
    [
        (("20220103|ABC|-1|0|100|Q",), "FINRA_VOLUME_NEGATIVE"),
        (("20220103|ABC|101|0|100|Q",), "FINRA_SHORT_OVER_TOTAL"),
        (
            ("20220103|ABC|1|0|2|Q", "20220103|ABC|1|0|2|N"),
            "FINRA_DUPLICATE_DATE_SYMBOL",
        ),
    ],
)
def test_parse_daily_file_rejects_invalid_rows(rows: tuple[str, ...], reason: str) -> None:
    with pytest.raises(ValueError, match=reason):
        parse_daily_file(_body(*rows), date(2022, 1, 3))


def test_fetch_daily_file_retries_and_records_causal_availability() -> None:
    calls: list[date] = []

    def transport(day: date) -> HttpPayload:
        calls.append(day)
        if len(calls) == 1:
            raise HTTPError("https://fixed.invalid", 429, "limited", {}, None)
        return _payload(_body("20220103|ABC|50|2|100|Q"))

    sleeps: list[float] = []
    frame, manifest = fetch_daily_file(
        transport,
        date(2022, 1, 3),
        sleep=sleeps.append,
        base_backoff_seconds=0.25,
    )

    assert len(frame) == 1
    assert calls == [date(2022, 1, 3), date(2022, 1, 3)]
    assert sleeps == [0.25]
    assert manifest["last_modified"] == "2022-01-03T22:19:58+00:00"
    assert manifest["complete"] is True
    assert len(str(manifest["response_sha256"])) == 64


def test_fetch_daily_file_retries_remote_disconnect() -> None:
    calls = 0

    def transport(day: date) -> HttpPayload:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RemoteDisconnected("peer closed")
        return _payload(_body(f"{day:%Y%m%d}|ABC|50|2|100|Q"))

    sleeps: list[float] = []
    frame, _ = fetch_daily_file(
        transport,
        date(2022, 1, 3),
        sleep=sleeps.append,
        base_backoff_seconds=0.5,
    )

    assert len(frame) == 1
    assert calls == 2
    assert sleeps == [0.5]


def test_acquire_sessions_resumes_hash_verified_partition(tmp_path) -> None:
    calls = 0

    def transport(day: date) -> HttpPayload:
        nonlocal calls
        calls += 1
        return _payload(_body(f"{day:%Y%m%d}|ABC|50|2|100|Q"))

    manifests = acquire_sessions(tmp_path, [date(2022, 1, 3)], transport)

    assert manifests[0]["training_only"] is True
    assert acquire_sessions(tmp_path, [date(2022, 1, 3)], transport) == manifests
    assert calls == 1

    partition = tmp_path / "data/staging/finra_short_volume_v1/2022/2022-01-04.parquet"
    partition.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"x": [1]}).to_parquet(partition)
    with pytest.raises(ValueError, match="PARTIAL_FINRA_DAY"):
        acquire_sessions(tmp_path, [date(2022, 1, 4)], transport)

    with pytest.raises(ValueError, match="TRAINING_ONLY"):
        acquire_sessions(tmp_path, [date(2024, 1, 2)], transport)
