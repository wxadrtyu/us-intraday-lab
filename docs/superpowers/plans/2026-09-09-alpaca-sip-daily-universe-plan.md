# Alpaca SIP Daily Universe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an immutable, read-only Alpaca SIP daily-bar dataset and use it to publish and audit a point-in-time monthly US-equity universe without relying on IEX liquidity.

**Architecture:** Add a SIP-specific daily acquisition module instead of parameterizing or overwriting the existing IEX path. Generalize monthly-universe construction only at its source boundary, then publish the SIP universe in its own immutable namespace. A separate audit compares expected assets, SIP observations, eligibility decisions, and the legacy IEX universe; no strategy version is permitted until the audit passes.

**Tech Stack:** Python 3.12, alpaca-py historical market-data client, pandas, DuckDB, PyArrow/Parquet, pytest, Ruff, PowerShell.

## Global Constraints

- Market-data reads only; importing or constructing an Alpaca trading client is forbidden.
- Source feed is exactly `sip`; no IEX/SIP row splicing.
- Raw data root is `E:\us-intraday-lab-data\us-market`; raw data and runtime state remain untracked.
- Existing `alpaca_iex_1day_v2` and IEX monthly-universe datasets remain immutable.
- Credentials come only from `ALPACA_PAPER_API_KEY` and `ALPACA_PAPER_SECRET_KEY` in the active environment and never enter logs or manifests.
- Historical requests use explicit `asof`; current active/tradable flags cannot remove historical bars.
- Missing data remains missing; no zero fill, forward fill, or missing-as-cash semantics.
- 2018-2020 and 2026 data cannot participate in fit or parameter ranking.
- No v18010 strategy version may be created until the SIP universe audit sets `strategy_metrics_permitted=true`.

---

### Task 1: SIP-only historical daily downloader

**Files:**
- Create: `src/us_intraday_lab/data/alpaca_sip_daily.py`
- Create: `tests/unit/data/test_alpaca_sip_daily.py`

**Interfaces:**
- Consumes: Alpaca `StockHistoricalDataClient.get_stock_bars(request)` and active credential environment.
- Produces: `ReadOnlyAlpacaSipDailyDownloader.from_environment(*, environ: Mapping[str, str] | None = None, client_factory: HistoricalClientFactory = _client_factory)` and `fetch(*, symbols: tuple[str, ...], start: date, end: date, asof: date) -> pandas.DataFrame`.

- [ ] **Step 1: Write the failing feed and normalization tests**

```python
def test_sip_daily_request_is_sip_and_preserves_asof() -> None:
    client = FakeHistoricalClient(frame=_daily_frame())
    result = ReadOnlyAlpacaSipDailyDownloader(client).fetch(
        symbols=("AAPL", "OLD"),
        start=date(2022, 1, 1),
        end=date(2022, 1, 31),
        asof=date(2022, 1, 31),
    )
    assert str(client.request.feed).lower().endswith("sip")
    assert client.request.asof == "2022-01-31"
    assert client.request.end.date() == date(2022, 2, 1)
    assert set(result["feed"]) == {"sip"}
    assert set(result["provider"]) == {"alpaca"}
    assert set(result["asof"]) == {date(2022, 1, 31)}

def test_sip_daily_environment_fails_closed_without_credentials() -> None:
    with pytest.raises(RuntimeError, match="ALPACA_SIP_DAILY_CREDENTIAL_MISSING"):
        ReadOnlyAlpacaSipDailyDownloader.from_environment(environ={})
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `$env:PYTHONPATH='src'; python -m pytest tests/unit/data/test_alpaca_sip_daily.py -q`

Expected: collection fails because `us_intraday_lab.data.alpaca_sip_daily` does not exist.

- [ ] **Step 3: Implement the minimal SIP-only downloader**

```python
class ReadOnlyAlpacaSipDailyDownloader:
    def __init__(self, client: HistoricalBarsClient) -> None:
        self._client = client

    @classmethod
    def from_environment(cls, *, environ=None, client_factory=_client_factory):
        values = os.environ if environ is None else environ
        api_key = values.get(API_KEY_VARIABLE, "")
        secret_key = values.get(SECRET_KEY_VARIABLE, "")
        if not api_key or not secret_key:
            raise RuntimeError("ALPACA_SIP_DAILY_CREDENTIAL_MISSING")
        return cls(client_factory(api_key, secret_key))

    def fetch(self, *, symbols, start, end, asof):
        request = StockBarsRequest(
            symbol_or_symbols=list(symbols), timeframe=TimeFrame.Day,
            start=datetime.combine(start, datetime_time(), UTC),
            end=datetime.combine(end + timedelta(days=1), datetime_time(), UTC),
            adjustment=Adjustment.SPLIT, feed=DataFeed.SIP,
            asof=asof.isoformat(),
        )
        return normalize_sip_daily(self._client.get_stock_bars(request)._raw_data, asof=asof)
```

The production implementation may normalize from `response.df.reset_index()` as the existing Alpaca adapter does; it must retain only bar data and provenance fields.

- [ ] **Step 4: Run tests and static checks**

Run: `$env:PYTHONPATH='src'; python -m pytest tests/unit/data/test_alpaca_sip_daily.py -q`

Expected: all Task 1 tests pass.

Run: `python -m ruff check src/us_intraday_lab/data/alpaca_sip_daily.py tests/unit/data/test_alpaca_sip_daily.py`

Expected: `All checks passed!`

- [ ] **Step 5: Commit Task 1**

```powershell
git add -- src/us_intraday_lab/data/alpaca_sip_daily.py tests/unit/data/test_alpaca_sip_daily.py
git commit -m "Add SIP-only daily market-data downloader"
```

### Task 2: Immutable SIP daily partitions and CLI

**Files:**
- Modify: `src/us_intraday_lab/data/alpaca_sip_daily.py`
- Create: `scripts/acquire_us_market_sip_daily.py`
- Modify: `tests/unit/data/test_alpaca_sip_daily.py`
- Create: `research/protocols/us_market_sip_daily_v1.json`

**Interfaces:**
- Consumes: `ReadOnlyAlpacaSipDailyDownloader.fetch(*, symbols: tuple[str, ...], start: date, end: date, asof: date)` and sorted candidate symbols from the frozen asset catalog.
- Produces: `acquire_sip_daily_shards(root, downloader, symbols, start, end, batch_size=100) -> list[dict[str, object]]` under `data/staging/alpaca_sip_1day_v1`.

- [ ] **Step 1: Write failing immutable-publication tests**

```python
def test_sip_daily_shard_is_immutable_and_resume_safe(tmp_path: Path) -> None:
    downloader = FakeSipDownloader(_daily_frame())
    first = acquire_sip_daily_shards(
        root=tmp_path, downloader=downloader, symbols=("AAPL",),
        start=date(2022, 1, 1), end=date(2022, 12, 31), batch_size=100,
    )
    second = acquire_sip_daily_shards(
        root=tmp_path, downloader=downloader, symbols=("AAPL",),
        start=date(2022, 1, 1), end=date(2022, 12, 31), batch_size=100,
    )
    assert first == second
    assert downloader.calls == 1
    assert first[0]["feed"] == "sip"
    assert first[0]["content_sha256"]

def test_sip_daily_partial_shard_fails_closed(tmp_path: Path) -> None:
    identity = hashlib.sha256(b"AAPL").hexdigest()[:16]
    partial = (
        tmp_path
        / "data/staging/alpaca_sip_1day_v1"
        / f"2022-batch-0000-{identity}.parquet"
    )
    partial.parent.mkdir(parents=True)
    partial.touch()
    with pytest.raises(ValueError, match="partial SIP daily shard"):
        acquire_sip_daily_shards(
            root=tmp_path,
            downloader=FakeSipDownloader(_daily_frame()),
            symbols=("AAPL",),
            start=date(2022, 1, 1),
            end=date(2022, 12, 31),
            batch_size=100,
        )
```

- [ ] **Step 2: Run tests and verify RED**

Run: `$env:PYTHONPATH='src'; python -m pytest tests/unit/data/test_alpaca_sip_daily.py -q`

Expected: fails because immutable shard acquisition is not implemented.

- [ ] **Step 3: Implement partition acquisition**

Use deterministic year/batch names, temporary Parquet and JSON files, SHA-256 verification on resume, bounded retry, explicit invalid-symbol recording, and this manifest identity:

```python
record = {
    "schema_version": "1.0.0", "provider": "alpaca", "feed": "sip",
    "bar_size": "1day", "adjustment": "split", "year": year,
    "start": period_start.isoformat(), "end": period_end.isoformat(),
    "asof": asof.isoformat(), "symbols": list(batch),
    "provider_rejected_symbols": sorted(rejected), "row_count": len(frame),
    "content_sha256": sha256_file(parquet),
    "read_only_market_data": True,
}
```

- [ ] **Step 4: Add the CLI and frozen protocol**

The CLI resolves the latest asset snapshot explicitly supplied with `--assets`, derives primary-exchange queryable symbols without filtering current status/tradability, and prints only counts and manifest paths. It must never print credentials.

- [ ] **Step 5: Run targeted and existing acquisition tests**

Run: `$env:PYTHONPATH='src'; python -m pytest tests/unit/data/test_alpaca_sip_daily.py tests/unit/data/test_us_market_acquisition.py -q`

Expected: all tests pass.

- [ ] **Step 6: Commit Task 2**

```powershell
git add -- src/us_intraday_lab/data/alpaca_sip_daily.py tests/unit/data/test_alpaca_sip_daily.py scripts/acquire_us_market_sip_daily.py research/protocols/us_market_sip_daily_v1.json
git commit -m "Publish immutable SIP daily market shards"
```

### Task 3: Source-explicit monthly universe builder

**Files:**
- Modify: `src/us_intraday_lab/data/monthly_universe.py`
- Modify: `tests/unit/data/test_monthly_universe.py`
- Create: `scripts/build_us_market_sip_monthly_universe.py`

**Interfaces:**
- Consumes: `build_monthly_universe(root: Path, start_month: date, end_month: date, source: str = "alpaca_iex_1day_v2")`.
- Produces: immutable decisions under `data/catalog/monthly_universe_sip_v1/<dataset_id>/decisions.parquet` plus manifest.

- [ ] **Step 1: Write failing source-boundary tests**

```python
def test_sip_universe_reads_only_sip_namespace(tmp_path: Path) -> None:
    write_daily(tmp_path, "alpaca_iex_1day_v2", symbol="IEXONLY", volume=9e9)
    write_daily(tmp_path, "alpaca_sip_1day_v1", symbol="SIPONLY", volume=2e6)
    manifest = build_monthly_universe(
        root=tmp_path, start_month=date(2022, 2, 1),
        end_month=date(2022, 2, 1), source="alpaca_sip_1day_v1",
    )
    decisions = load_decisions(tmp_path, manifest, namespace="monthly_universe_sip_v1")
    assert set(decisions["symbol"]) == {"SIPONLY"}
    assert manifest["source_feed"] == "sip"

def test_current_asset_status_is_not_an_eligibility_input(tmp_path: Path) -> None:
    write_daily(tmp_path, "alpaca_sip_1day_v1", symbol="OLD", volume=2_000_000.0)
    manifest = build_monthly_universe(
        root=tmp_path,
        start_month=date(2022, 2, 1),
        end_month=date(2022, 2, 1),
        source="alpaca_sip_1day_v1",
    )
    decisions = load_decisions(
        tmp_path, manifest, namespace="monthly_universe_sip_v1"
    ).set_index("symbol")
    assert bool(decisions.loc["OLD", "eligible"])
    assert manifest["uses_current_asset_status"] is False
```

- [ ] **Step 2: Run tests and verify RED**

Run: `$env:PYTHONPATH='src'; python -m pytest tests/unit/data/test_monthly_universe.py -q`

Expected: fails because `source` is not accepted and the SIP namespace does not exist.

- [ ] **Step 3: Implement explicit source mapping**

```python
SOURCE_CONTRACTS = {
    "alpaca_iex_1day_v2": ("alpaca_iex_1day_v2", "monthly_universe", "iex"),
    "alpaca_sip_1day_v1": ("alpaca_sip_1day_v1", "monthly_universe_sip_v1", "sip"),
}
```

Reject unknown sources, read only the selected staging path, preserve the existing rolling calculation, and include `source_dataset`, `source_feed`, and `uses_current_asset_status=false` in the manifest.

- [ ] **Step 4: Run tests and lint**

Run: `$env:PYTHONPATH='src'; python -m pytest tests/unit/data/test_monthly_universe.py tests/unit/data/test_us_market_acquisition.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit Task 3**

```powershell
git add -- src/us_intraday_lab/data/monthly_universe.py tests/unit/data/test_monthly_universe.py scripts/build_us_market_sip_monthly_universe.py
git commit -m "Build monthly universe from SIP liquidity"
```

### Task 4: Production coverage and source-bias audit

**Files:**
- Create: `src/us_intraday_lab/data/sip_universe_audit.py`
- Create: `tests/unit/data/test_sip_universe_audit.py`
- Create: `scripts/audit_us_market_sip_universe.py`

**Interfaces:**
- Consumes: SIP daily manifests and Parquet, SIP monthly decisions, asset catalog, and optional legacy IEX decisions.
- Produces: an immutable JSON/Markdown audit with `strategy_metrics_permitted` and exact rejection reasons.

- [ ] **Step 1: Write failing audit-gate tests**

```python
def test_audit_blocks_missing_month_and_survivorship_uncertainty() -> None:
    result = audit_sip_universe(
        expected_months=(date(2022, 1, 1), date(2022, 2, 1)),
        observed_months=(date(2022, 1, 1),),
        sip_daily=pd.DataFrame(),
        iex_daily=pd.DataFrame(),
        independent_historical_master=False,
        hashes_valid=True,
        partial_partitions=0,
    )
    assert result["strategy_metrics_permitted"] is False
    assert "EXPECTED_MONTH_MISSING" in result["rejection_reasons"]
    assert result["survivorship"]["independent_historical_master"] is False

def test_audit_reports_sip_to_iex_volume_ratio_without_splicing() -> None:
    sip = pd.DataFrame(
        {"symbol": ["AAPL"], "session_date": [date(2022, 1, 3)], "volume": [4000.0]}
    )
    iex = pd.DataFrame(
        {"symbol": ["AAPL"], "session_date": [date(2022, 1, 3)], "volume": [100.0]}
    )
    result = audit_sip_universe(
        expected_months=(date(2022, 1, 1),),
        observed_months=(date(2022, 1, 1),),
        sip_daily=sip,
        iex_daily=iex,
        independent_historical_master=True,
        hashes_valid=True,
        partial_partitions=0,
    )
    assert result["source_bias"]["median_sip_to_iex_volume_ratio"] == pytest.approx(40.0)
    assert result["rows_spliced"] == 0
```

- [ ] **Step 2: Run tests and verify RED**

Run: `$env:PYTHONPATH='src'; python -m pytest tests/unit/data/test_sip_universe_audit.py -q`

Expected: collection fails because the audit module does not exist.

- [ ] **Step 3: Implement the audit**

The audit must report expected/observed years, months, sessions, assets, monthly eligible counts, missing/rejected symbols, zero-row partitions, current inactive observations, liquidity-decile coverage, SIP/IEX volume ratios on matched keys, and exact data-gate failures. `strategy_metrics_permitted` is true only when all required periods exist, hashes validate, no partial partitions exist, and the independently declared survivorship condition passes.

- [ ] **Step 4: Run tests and lint**

Run: `$env:PYTHONPATH='src'; python -m pytest tests/unit/data/test_sip_universe_audit.py tests/unit/data/test_monthly_universe.py tests/unit/data/test_alpaca_sip_daily.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit Task 4**

```powershell
git add -- src/us_intraday_lab/data/sip_universe_audit.py tests/unit/data/test_sip_universe_audit.py scripts/audit_us_market_sip_universe.py
git commit -m "Audit SIP full-market universe readiness"
```

### Task 5: Entitlement check, bulk acquisition, universe publication, and final verification

**Files:**
- Create from runtime: external immutable SIP partitions and universe catalog under `E:\us-intraday-lab-data\us-market`
- Create: `research/results/2026-09-09-alpaca-sip-universe-audit.json`
- Create: `research/results/2026-09-09-alpaca-sip-universe-audit.md`

**Interfaces:**
- Consumes: Tasks 1-4 CLIs.
- Produces: verified data readiness decision and the input dataset ID for the next decision-quote acquisition plan.

- [ ] **Step 1: Run a read-only entitlement check**

Run one past-date SIP daily request for two symbols. Print only feed, row count, date bounds, and columns.

Expected: feed `sip`, non-zero rows, no credential text.

- [ ] **Step 2: Start/resume the full SIP daily acquisition**

```powershell
$env:PYTHONPATH='src'
python scripts/acquire_us_market_sip_daily.py --root 'E:\us-intraday-lab-data\us-market' --assets 'E:\us-intraday-lab-data\us-market\data\catalog\us_equity_assets\alpaca-us-equity-assets-4cf36da00fead42b3b669620\assets.parquet' --start 2018-01-01 --end 2026-03-31 --batch-size 100
```

Expected: atomic progress per year/batch; existing verified shards resume without new calls.

- [ ] **Step 3: Verify all shard hashes and publish the SIP universe**

```powershell
python scripts/build_us_market_sip_monthly_universe.py --root 'E:\us-intraday-lab-data\us-market' --start-month 2018-04-01 --end-month 2026-03-01
```

Expected: a new immutable `monthly_universe_sip_v1` dataset ID; IEX catalogs remain unchanged.

- [ ] **Step 4: Run and publish the audit**

```powershell
python scripts/audit_us_market_sip_universe.py --root 'E:\us-intraday-lab-data\us-market' --output-json research/results/2026-09-09-alpaca-sip-universe-audit.json --output-md research/results/2026-09-09-alpaca-sip-universe-audit.md
```

Expected: truthful pass/fail with exact missing coverage and survivorship reasons. A fail does not trigger imputation or strategy research.

- [ ] **Step 5: Run full verification**

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/unit/data/test_alpaca_sip_daily.py tests/unit/data/test_monthly_universe.py tests/unit/data/test_sip_universe_audit.py tests/unit/data/test_us_market_acquisition.py -q
python -m ruff check src/us_intraday_lab/data/alpaca_sip_daily.py src/us_intraday_lab/data/monthly_universe.py src/us_intraday_lab/data/sip_universe_audit.py scripts/acquire_us_market_sip_daily.py scripts/build_us_market_sip_monthly_universe.py scripts/audit_us_market_sip_universe.py tests/unit/data/test_alpaca_sip_daily.py tests/unit/data/test_monthly_universe.py tests/unit/data/test_sip_universe_audit.py
```

Expected: all tests pass and Ruff reports `All checks passed!`.

- [ ] **Step 6: Commit and push publishable evidence**

```powershell
git add -- research/results/2026-09-09-alpaca-sip-universe-audit.json research/results/2026-09-09-alpaca-sip-universe-audit.md
git commit -m "Publish SIP universe readiness audit"
git push
```

## Follow-on plan

If and only if Task 5 produces a valid SIP monthly-universe dataset, write a separate implementation plan for full-market decision, entry, and exit SIP quote acquisition. Strategy v18010 remains blocked until that second data plan completes and its event-level coverage audit passes.
