# Alpaca SIP Five-Minute Full-Market Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish and audit an immutable Alpaca SIP five-minute full-market dataset, then expose a causal research cube without permitting a strategy before every data gate passes.

**Architecture:** A SIP-only downloader writes deterministic calendar-month and symbol-batch partitions under a new external namespace. A validator independently reconstructs every request identity and checks file contents; a coverage audit joins the frozen monthly universe to the XNYS grid and fails closed on missing clocks or historical-master evidence. A read-only DuckDB view becomes the only research entry point after audit approval.

**Tech Stack:** Python 3.12, alpaca-py historical market-data client, pandas, DuckDB, PyArrow/Parquet, exchange-calendars, pytest, Ruff, PowerShell.

## Global Constraints

- Market-data reads only; no trading client, broker, order, submit, or cancel code.
- Source is exactly Alpaca SIP five-minute split-adjusted bars; no IEX/SIP splicing.
- Raw data root is `E:\us-intraday-lab-data\us-market`; raw data and runtime state stay untracked.
- Candidate requests use all 15,399 frozen asset-snapshot symbols, including inactive records.
- Every production request carries its declared end as explicit `asof`—calendar
  month-end for complete months and requested end for a bounded pilot/partial month.
- Missing data is preserved; no fill, cash substitution, or silent symbol/session removal.
- Fit is 2022-2023; selection is 2024-2025; 2018-2020 and 2026 are post-freeze diagnostics only.
- `strategy_metrics_permitted` remains false until five-minute coverage and an independently validated historical security master both pass.

---

### Task 1: SIP five-minute downloader and immutable partitions

**Files:**
- Create: `src/us_intraday_lab/data/alpaca_sip_five_minute.py`
- Create: `tests/unit/data/test_alpaca_sip_five_minute.py`
- Create: `scripts/acquire_us_market_sip_five_minute.py`
- Create: `research/protocols/us_market_sip_5min_v1.json`

**Interfaces:**
- Produces: `ReadOnlyAlpacaSipFiveMinuteDownloader.from_environment(*, environ: Mapping[str, str] | None = None, client_factory: HistoricalClientFactory = _client_factory)`.
- Produces: `fetch(*, symbols: tuple[str, ...], start: date, end: date, asof: date) -> pd.DataFrame`.
- Produces: `acquire_sip_five_minute_shards(*, root, downloader, symbols, start, end, batch_size, shard_start=0, shard_stop=None) -> list[dict[str, object]]`.
- Produces: `validate_sip_five_minute_source(*, root, symbols, start, end, batch_size) -> dict[str, int]`.

- [ ] **Step 1: Write the failing downloader and immutability tests**

```python
def test_request_is_split_adjusted_sip_five_minutes_and_preserves_asof():
    client = FakeHistoricalClient(frame=_five_minute_frame())
    result = ReadOnlyAlpacaSipFiveMinuteDownloader(client).fetch(
        symbols=("AAA",), start=date(2025, 1, 2), end=date(2025, 1, 2),
        asof=date(2025, 1, 31),
    )
    assert client.request.timeframe.amount == 5
    assert str(client.request.feed).lower().endswith("sip")
    assert client.request.asof == "2025-01-31"
    assert set(result["feed"]) == {"sip"}

def test_resume_rejects_a_request_identity_collision(tmp_path):
    records = acquire_sip_five_minute_shards(
        root=tmp_path, downloader=FakeDownloader(_five_minute_frame()),
        symbols=("AAA",), start=date(2025, 1, 1), end=date(2025, 1, 31),
        batch_size=100,
    )
    manifest = Path(records[0]["manifest_path"])
    payload = json.loads(manifest.read_text("utf-8"))
    payload["request"]["feed"] = "iex"
    manifest.write_text(json.dumps(payload), "utf-8")
    with pytest.raises(ValueError, match="request identity"):
        acquire_sip_five_minute_shards(
            root=tmp_path, downloader=FakeDownloader(_five_minute_frame()),
            symbols=("AAA",), start=date(2025, 1, 1), end=date(2025, 1, 31),
            batch_size=100,
        )
```

- [ ] **Step 2: Run RED**

Run: `$env:PYTHONPATH='src'; python -m pytest tests/unit/data/test_alpaca_sip_five_minute.py -q`

Expected: collection fails because `alpaca_sip_five_minute` does not exist.

- [ ] **Step 3: Implement the downloader and partition writer**

Use `StockBarsRequest`, `TimeFrame(5, TimeFrameUnit.Minute)`, `DataFeed.SIP`, `Adjustment.SPLIT`, exclusive end-plus-one-day, and explicit `asof`. Normalize to symbol, UTC timestamp, OHLCV, trade count, VWAP, asof, provider, and feed. Use request-hashed immutable Parquet/JSON pairs, bounded invalid-symbol handling, atomic rename, and optional shard bounds for independent resumable workers.

- [ ] **Step 4: Add the CLI and frozen protocol**

The CLI requires explicit asset snapshot, date bounds, batch size, and optional shard bounds. It prints counts only and never credentials. The protocol copies all date-role, source, missingness, and Paper-prohibition constraints from the approved design.

- [ ] **Step 5: Run GREEN and lint**

Run: `$env:PYTHONPATH='src'; python -m pytest tests/unit/data/test_alpaca_sip_five_minute.py -q`

Run: `python -m ruff check src/us_intraday_lab/data/alpaca_sip_five_minute.py tests/unit/data/test_alpaca_sip_five_minute.py scripts/acquire_us_market_sip_five_minute.py`

Expected: all tests and Ruff pass.

- [ ] **Step 6: Commit**

```powershell
git add -- src/us_intraday_lab/data/alpaca_sip_five_minute.py tests/unit/data/test_alpaca_sip_five_minute.py scripts/acquire_us_market_sip_five_minute.py research/protocols/us_market_sip_5min_v1.json
git commit -m "Add immutable full-market SIP five-minute acquisition"
```

### Task 2: Capacity pilot and safe bulk launch

**Files:**
- Create: `scripts/estimate_us_market_sip_five_minute_capacity.py`
- Create: `tests/unit/data/test_sip_five_minute_capacity.py`
- Create after execution: `research/results/2026-09-13-alpaca-sip-5min-capacity.json`

**Interfaces:**
- Produces: `estimate_capacity(*, sampled_rows, sampled_symbols, sampled_sessions, expected_symbol_sessions) -> dict[str, float | int]`.

- [ ] **Step 1: Write a failing deterministic capacity-estimate test**

```python
def test_capacity_estimate_scales_observed_symbol_sessions():
    result = estimate_capacity(
        sampled_rows=7800, sampled_symbols=10, sampled_sessions=10,
        expected_symbol_sessions=1_000_000,
    )
    assert result["estimated_rows"] == 78_000_000
    assert result["rows_per_symbol_session"] == 78
```

- [ ] **Step 2: Run RED, implement the pure estimator, then run GREEN**

Run: `$env:PYTHONPATH='src'; python -m pytest tests/unit/data/test_sip_five_minute_capacity.py -q`

The pilot samples one complete closed session across liquidity deciles in the
isolated external root `E:\us-intraday-lab-data\us-market-sip-5min-pilot`,
measures rows, bytes, API time, and free disk, and writes only aggregate
statistics. The pilot root must never be copied into the production namespace.
It must stop before bulk launch if projected bytes exceed 70% of free space.

- [ ] **Step 3: Run a one-session SIP pilot**

Run the acquisition CLI for one fully closed 2025 session using deterministic shard bounds, validate every pilot partition, and write the immutable capacity result.

- [ ] **Step 4: Launch the bulk job from atomic checkpoints**

Launch only after the capacity check passes. Use bounded shard ranges so each worker owns disjoint deterministic request identities. Confirm process IDs and the first completed hash-valid partitions before leaving the job running.

- [ ] **Step 5: Commit publishable pilot code and report**

```powershell
git add -- scripts/estimate_us_market_sip_five_minute_capacity.py tests/unit/data/test_sip_five_minute_capacity.py research/results/2026-09-13-alpaca-sip-5min-capacity.json
git commit -m "Validate SIP five-minute acquisition capacity"
```

### Task 3: Full-market five-minute coverage audit

**Files:**
- Create: `src/us_intraday_lab/data/sip_five_minute_audit.py`
- Create: `tests/unit/data/test_sip_five_minute_audit.py`
- Create: `scripts/audit_us_market_sip_five_minute.py`
- Create after completion: `research/results/2026-09-13-alpaca-sip-5min-audit.json`
- Create after completion: `research/results/2026-09-13-alpaca-sip-5min-audit.md`

**Interfaces:**
- Produces: `audit_sip_five_minute(*, bars, monthly_decisions, assets, expected_sessions, historical_master_validated) -> dict[str, object]`.

- [ ] **Step 1: Write failing tests for required-clock coverage and fail-closed gates**

```python
def test_audit_rejects_missing_delayed_entry_clock():
    result = audit_sip_five_minute(
        bars=bars_without_required_clock(), monthly_decisions=eligible_decisions(),
        assets=assets(), expected_sessions=(date(2025, 1, 2),),
        historical_master_validated=True,
    )
    assert not result["strategy_metrics_permitted"]
    assert "REQUIRED_CLOCK_COVERAGE_BELOW_95_PERCENT" in result["rejection_reasons"]

def test_audit_never_accepts_self_attested_historical_master():
    result = audit_sip_five_minute(
        bars=complete_required_clock_bars(),
        monthly_decisions=eligible_decisions(), assets=assets(),
        expected_sessions=(date(2025, 1, 2),),
        historical_master_validated=False,
    )
    assert "INDEPENDENT_HISTORICAL_MASTER_MISSING" in result["rejection_reasons"]
```

- [ ] **Step 2: Run RED, implement audit, then run GREEN**

The audit computes exact expected eligible symbol-session-clock keys, coverage by all required segments, duplicate/off-grid/invalid OHLC findings, request/hash validity, and source exclusivity. It reports missingness without materializing it as zero bars.

- [ ] **Step 3: Run the production audit only after bulk completion**

Verify the acquisition completion manifest first. The audit must remain blocked if any partition or the independent historical-master evidence is missing.

- [ ] **Step 4: Commit code and bounded reports**

```powershell
git add -- src/us_intraday_lab/data/sip_five_minute_audit.py tests/unit/data/test_sip_five_minute_audit.py scripts/audit_us_market_sip_five_minute.py research/results/2026-09-13-alpaca-sip-5min-audit.json research/results/2026-09-13-alpaca-sip-5min-audit.md
git commit -m "Audit full-market SIP five-minute readiness"
```

### Task 4: Gated causal research view

**Files:**
- Create: `src/us_intraday_lab/data/sip_five_minute_research.py`
- Create: `tests/unit/data/test_sip_five_minute_research.py`
- Create: `scripts/build_us_market_sip_five_minute_research_catalog.py`

**Interfaces:**
- Produces: `open_sip_five_minute_research_view(*, root, audit_path, role) -> duckdb.DuckDBPyConnection`.

- [ ] **Step 1: Write failing tests for audit and date-role enforcement**

```python
def test_view_refuses_a_blocked_audit(tmp_path):
    write_audit(tmp_path, strategy_metrics_permitted=False)
    with pytest.raises(RuntimeError, match="SIP_FIVE_MINUTE_AUDIT_BLOCKED"):
        open_sip_five_minute_research_view(
            root=tmp_path, audit_path=tmp_path / "audit.json", role="fit"
        )

def test_fit_view_contains_only_2022_and_2023(tmp_path):
    connection = open_sip_five_minute_research_view(
        root=tmp_path, audit_path=tmp_path / "audit.json", role="fit"
    )
    years = connection.execute("select distinct year(session_date) from research_bars").fetchall()
    assert years == [(2022,), (2023,)]
```

- [ ] **Step 2: Run RED, implement the read-only DuckDB view, then run GREEN**

The view verifies the audit hash, opens Parquet read-only, joins membership by month, exposes explicit availability, and applies fixed role bounds. It has no strategy version creation or ranking logic.

- [ ] **Step 3: Run the complete data test suite and lint**

Run: `$env:PYTHONPATH='src'; python -m pytest tests/unit/data -q`

Run: `python -m ruff check src/us_intraday_lab/data scripts tests/unit/data`

Expected: zero failures and zero Ruff errors.

- [ ] **Step 4: Commit and push**

```powershell
git add -- src/us_intraday_lab/data/sip_five_minute_research.py tests/unit/data/test_sip_five_minute_research.py scripts/build_us_market_sip_five_minute_research_catalog.py
git commit -m "Gate the SIP five-minute causal research view"
git push origin codex/v550-v649-second-strategy
```
