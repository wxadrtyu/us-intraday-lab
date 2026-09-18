from __future__ import annotations

from urllib.error import URLError

import scripts.acquire_sec_fundamental_filings_training as subject


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def read(self) -> bytes:
        return b"ok"


def test_sec_fetcher_retries_transient_transport_error(monkeypatch) -> None:
    calls = 0

    def fake_urlopen(_request, timeout):
        nonlocal calls
        assert timeout == 60
        calls += 1
        if calls == 1:
            raise URLError("temporary TLS EOF")
        return _Response()

    monkeypatch.setattr(subject, "urlopen", fake_urlopen)
    monkeypatch.setattr(subject.time, "sleep", lambda _seconds: None)

    assert subject.SecFetcher()("https://data.sec.gov/example") == b"ok"
    assert calls == 2
