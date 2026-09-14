# Polygon Historical Security Master Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Acquire and independently validate immutable monthly Polygon US-stock reference snapshots from January 2018 through March 2026, then use only the validator evidence to clear the existing historical-master audit gate.

**Architecture:** A single focused data module implements safe URL construction, read-only transport, raw-page publication, canonical snapshot derivation, and reconstruction-based validation. Thin scripts expose acquisition and audit commands. Existing SIP audit scripts consume the immutable validator report rather than a caller assertion.

**Tech Stack:** Python 3.12 standard-library HTTPS, pandas, PyArrow, pytest, Ruff.

**Frozen requirements:** Query `/v3/reference/tickers` with `market=stocks`, `locale=us`, both activity states, `limit=1000`, ticker-ascending order, and month-end as-of dates from `2018-01-31` through `2026-03-31`. Read `POLYGON_API_KEY` only from the environment and send it only as an Authorization header. Preserve raw pages, hashes, nulls, unmatched symbols, and failures. Never splice providers, fill missing records, infer history, modify existing source artifacts, activate Paper, or add execution capability.

---

## File structure

- Create `src/us_intraday_lab/data/polygon_historical_master.py`: pure identities, normalization, acquisition, snapshot construction, and independent validation.
- Create `tests/unit/data/test_polygon_historical_master.py`: test-first coverage of every module behavior.
- Create `scripts/acquire_polygon_historical_master.py`: acquisition CLI with secret-safe output.
- Create `scripts/audit_polygon_historical_master.py`: immutable validator report and cross-source comparison CLI.
- Create `tests/unit/test_polygon_historical_master_scripts.py`: CLI helpers and report behavior.
- Modify `scripts/audit_us_market_sip_five_minute.py`: require and verify a Polygon validation report.
- Modify `scripts/audit_us_market_sip_universe.py`: require and verify the same report.
- Modify the associated audit tests: prove a boolean or malformed report cannot clear either gate.
- Create `research/protocols/polygon_historical_master_v1.json`: frozen acquisition and validation contract.
- Create immutable pilot/full result JSON and Markdown under `research/results/` only after live validation.

### Task 1: Pure request, calendar, and normalization contract

**Files:**
- Create: `tests/unit/data/test_polygon_historical_master.py`
- Create: `src/us_intraday_lab/data/polygon_historical_master.py`

**Interfaces:**
- Produces: `month_end_dates(start: date, end: date) -> tuple[date, ...]`
- Produces: `initial_request_identity(asof: date, active: bool) -> dict[str, object]`
- Produces: `request_url(identity: Mapping[str, object]) -> str`
- Produces: `validate_page_url(url: str) -> str`
- Produces: `normalize_page(payload: Mapping[str, object], *, asof: date, active: bool) -> pd.DataFrame`

- [ ] **Step 1: Write failing contract tests**

```python
def test_month_ends_are_complete_and_clamped() -> None:
    assert month_end_dates(date(2018, 1, 1), date(2018, 3, 15)) == (
        date(2018, 1, 31), date(2018, 2, 28), date(2018, 3, 15)
    )

def test_request_identity_is_deterministic_and_secret_free() -> None:
    identity = initial_request_identity(date(2018, 1, 31), False)
    assert identity == {
        "market": "stocks", "locale": "us", "date": "2018-01-31",
        "active": False, "limit": 1000, "sort": "ticker", "order": "asc",
    }
    assert "api" not in json.dumps(identity).lower()

def test_page_url_rejects_wrong_host_path_and_query_key() -> None:
    with pytest.raises(ValueError, match="POLYGON_PAGE_URL_FORBIDDEN"):
        validate_page_url("https://example.com/v3/reference/tickers")
    with pytest.raises(ValueError, match="POLYGON_PAGE_URL_CONTAINS_CREDENTIAL"):
        validate_page_url("https://api.polygon.io/v3/reference/tickers?apiKey=x")

def test_normalize_preserves_nulls_and_rejects_status_mismatch() -> None:
    frame = normalize_page(
        {"status": "OK", "results": [{"ticker": "ABC", "market": "stocks", "locale": "us", "active": False}]},
        asof=date(2018, 1, 31), active=False,
    )
    assert frame.loc[0, "primary_exchange"] is pd.NA
    assert frame.loc[0, "provider"] == "polygon"
    with pytest.raises(ValueError, match="POLYGON_ACTIVE_STATE_MISMATCH"):
        normalize_page(
            {"status": "OK", "results": [{"ticker": "ABC", "market": "stocks", "locale": "us", "active": True}]},
            asof=date(2018, 1, 31), active=False,
        )
```

- [ ] **Step 2: Run the tests and confirm RED**

Run: `python -m pytest tests/unit/data/test_polygon_historical_master.py -v`

Expected: collection fails because `us_intraday_lab.data.polygon_historical_master` does not exist.

- [ ] **Step 3: Implement the minimal pure contract**

Use `calendar.monthrange`, `urllib.parse.urlencode/urlsplit`, fixed output columns, explicit provider/status checks, uppercase tickers, nullable strings, and deterministic sorting. `validate_page_url` accepts only scheme `https`, host `api.polygon.io`, path `/v3/reference/tickers`, and rejects case-insensitive `apikey` query keys.

- [ ] **Step 4: Run the tests and confirm GREEN**

Run: `python -m pytest tests/unit/data/test_polygon_historical_master.py -v`

Expected: all Task 1 tests pass.

- [ ] **Step 5: Run targeted lint and commit**

Run: `python -m ruff check src/us_intraday_lab/data/polygon_historical_master.py tests/unit/data/test_polygon_historical_master.py`

Expected: exit 0.

Commit: `git add src/us_intraday_lab/data/polygon_historical_master.py tests/unit/data/test_polygon_historical_master.py && git commit -m "Add Polygon master data contract"`

### Task 2: Read-only transport, retry, raw publication, and resume

**Files:**
- Modify: `tests/unit/data/test_polygon_historical_master.py`
- Modify: `src/us_intraday_lab/data/polygon_historical_master.py`

**Interfaces:**
- Produces: `PolygonReferenceClient.from_environment(environ: Mapping[str, str] | None = None, transport: PageTransport = urllib_transport) -> PolygonReferenceClient`
- Produces: `PolygonReferenceClient.get_page(url: str) -> tuple[bytes, Mapping[str, str]]`
- Produces: `acquire_activity_pages(root: Path, client: PolygonReferenceClient, asof: date, active: bool, sleep: Callable[[float], None] = time.sleep) -> list[dict[str, object]]`
- Raw pair invariant: `page-NNNNN-<request-hash>.json` and `.manifest.json` are both present or acquisition fails.

- [ ] **Step 1: Add failing transport and resume tests**

```python
def test_client_requires_env_and_uses_bearer_header_only() -> None:
    with pytest.raises(RuntimeError, match="POLYGON_API_KEY_MISSING"):
        PolygonReferenceClient.from_environment(environ={})
    seen = {}
    def transport(url: str, headers: Mapping[str, str]) -> tuple[int, bytes, Mapping[str, str]]:
        seen.update(url=url, headers=dict(headers))
        return 200, b'{"status":"OK","results":[]}', {}
    client = PolygonReferenceClient.from_environment(
        environ={"POLYGON_API_KEY": "secret"}, transport=transport
    )
    client.get_page("https://api.polygon.io/v3/reference/tickers?limit=1000")
    assert "secret" not in seen["url"]
    assert seen["headers"]["Authorization"] == "Bearer secret"

def test_acquisition_publishes_page_pairs_and_resumes_without_network(tmp_path: Path) -> None:
    responses = two_page_response_transport()
    records = acquire_activity_pages(
        root=tmp_path, client=PolygonReferenceClient("secret", responses),
        asof=date(2018, 1, 31), active=True, sleep=lambda _: None,
    )
    assert len(records) == 2
    acquire_activity_pages(
        root=tmp_path, client=PolygonReferenceClient("secret", fail_transport),
        asof=date(2018, 1, 31), active=True, sleep=lambda _: None,
    )

def test_acquisition_rejects_partial_pair_and_hash_collision(tmp_path: Path) -> None:
    page = expected_page_path(tmp_path, date(2018, 1, 31), True, 1)
    page.parent.mkdir(parents=True)
    page.write_bytes(b"{}")
    with pytest.raises(ValueError, match="POLYGON_RAW_PAGE_PAIRING_FAILURE"):
        acquire_activity_pages(
            root=tmp_path, client=PolygonReferenceClient("secret", fail_transport),
            asof=date(2018, 1, 31), active=True, sleep=lambda _: None,
        )
```

- [ ] **Step 2: Run the new tests and confirm RED**

Run: `python -m pytest tests/unit/data/test_polygon_historical_master.py -v`

Expected: failures show the client and acquisition functions are missing.

- [ ] **Step 3: Implement minimal secure acquisition**

Implement a `urllib.request` transport with Authorization header, no query credential, explicit HTTP status handling, at most five retry attempts for transport failures/429/5xx, `Retry-After` support bounded to 60 seconds, and exponential fallback delays of 1, 2, 4, 8 seconds. Treat 401/403 and invalid provider payloads as permanent errors.

Hash the redacted request URL and raw body with SHA-256. Use same-directory `.tmp` files and `Path.replace` for page then manifest publication. Manifests record schema version, namespace, as-of, active state, page number, redacted URL, request hash, content hash, request ID, result count, next-page presence, and UTC retrieval timestamp.

- [ ] **Step 4: Run the tests and confirm GREEN**

Run: `python -m pytest tests/unit/data/test_polygon_historical_master.py -v`

Expected: all Task 1-2 tests pass with no secret in assertion output.

- [ ] **Step 5: Lint and commit**

Run: `python -m ruff check src/us_intraday_lab/data/polygon_historical_master.py tests/unit/data/test_polygon_historical_master.py`

Expected: exit 0.

Commit: `git add src/us_intraday_lab/data/polygon_historical_master.py tests/unit/data/test_polygon_historical_master.py && git commit -m "Acquire immutable Polygon reference pages"`

### Task 3: Canonical monthly snapshots and reconstruction validator

**Files:**
- Modify: `tests/unit/data/test_polygon_historical_master.py`
- Modify: `src/us_intraday_lab/data/polygon_historical_master.py`

**Interfaces:**
- Produces: `build_month_snapshot(root: Path, asof: date) -> dict[str, object]`
- Produces: `validate_historical_master(root: Path, start: date, end: date) -> dict[str, object]`
- Validation result includes `passed`, `months`, `raw_pages`, `rows`, `active_rows`, `inactive_rows`, `content_hashes_valid`, `page_chains_valid`, `snapshots_reconstructed`, `partial_files`, and `rejection_reasons`.

- [ ] **Step 1: Add failing snapshot and validator tests**

```python
def test_snapshot_is_exact_deterministic_derivation(tmp_path: Path) -> None:
    publish_fixture_pages(tmp_path, asof=date(2018, 1, 31))
    manifest = build_month_snapshot(tmp_path, date(2018, 1, 31))
    frame = pd.read_parquet(snapshot_path(tmp_path, date(2018, 1, 31)))
    assert list(frame[["ticker", "active"]].itertuples(index=False, name=None)) == [
        ("AAA", False), ("AAA", True), ("BBB", True)
    ]
    assert manifest["row_count"] == 3

def test_validator_reconstructs_grid_and_rejects_tampering(tmp_path: Path) -> None:
    publish_fixture_pages(tmp_path, asof=date(2018, 1, 31))
    build_month_snapshot(tmp_path, date(2018, 1, 31))
    assert validate_historical_master(
        tmp_path, date(2018, 1, 1), date(2018, 1, 31)
    )["passed"]
    snapshot_path(tmp_path, date(2018, 1, 31)).write_bytes(b"tampered")
    result = validate_historical_master(
        tmp_path, date(2018, 1, 1), date(2018, 1, 31)
    )
    assert not result["passed"]
    assert "SNAPSHOT_CONTENT_HASH_MISMATCH" in result["rejection_reasons"]
```

- [ ] **Step 2: Run the new tests and confirm RED**

Run: `python -m pytest tests/unit/data/test_polygon_historical_master.py -v`

Expected: failures identify missing snapshot and validation functions.

- [ ] **Step 3: Implement exact derivation and validation**

Read and validate every raw page pair before normalization. Reject broken chains, duplicate tickers within an activity state, state mismatches, unexpected market/locale, empty combined months, temporary files, or immutable collisions. Write Zstandard Parquet and a manifest containing the canonical file hash and ordered raw content hashes. Validator rebuilds the expected month grid from arguments and compares each Parquet snapshot with a fresh in-memory derivation from raw pages.

- [ ] **Step 4: Run tests and lint**

Run: `python -m pytest tests/unit/data/test_polygon_historical_master.py -v`

Expected: all tests pass.

Run: `python -m ruff check src/us_intraday_lab/data/polygon_historical_master.py tests/unit/data/test_polygon_historical_master.py`

Expected: exit 0.

- [ ] **Step 5: Commit**

Commit: `git add src/us_intraday_lab/data/polygon_historical_master.py tests/unit/data/test_polygon_historical_master.py && git commit -m "Validate Polygon historical master provenance"`

### Task 4: Acquisition and audit CLIs

**Files:**
- Create: `scripts/acquire_polygon_historical_master.py`
- Create: `scripts/audit_polygon_historical_master.py`
- Create: `tests/unit/test_polygon_historical_master_scripts.py`
- Create: `research/protocols/polygon_historical_master_v1.json`

**Interfaces:**
- Acquisition CLI arguments: `--root`, `--start`, `--end`, `--minimum-request-interval-seconds`.
- Audit CLI arguments: `--root`, `--start`, `--end`, `--assets`, `--decisions`, `--output-json`, `--output-md`.
- Audit report adds exact `alpaca_asset_symbols_not_in_polygon`, `polygon_symbols_not_in_alpaca_assets`, and `decision_symbols_not_in_polygon` arrays without changing either source.

- [ ] **Step 1: Write failing script tests**

```python
def test_immutable_writer_reuses_identical_and_rejects_collision(tmp_path: Path) -> None:
    path = tmp_path / "result.json"
    _write_immutable(path, "same\n")
    _write_immutable(path, "same\n")
    with pytest.raises(ValueError, match="immutable audit collision"):
        _write_immutable(path, "different\n")

def test_cross_source_comparison_preserves_unmatched_symbols() -> None:
    result = compare_symbols(
        polygon={"AAA", "OLD"}, alpaca={"AAA", "NEW"}, decisions={"AAA", "NEW"}
    )
    assert result["alpaca_asset_symbols_not_in_polygon"] == ["NEW"]
    assert result["polygon_symbols_not_in_alpaca_assets"] == ["OLD"]
    assert result["decision_symbols_not_in_polygon"] == ["NEW"]
```

- [ ] **Step 2: Run script tests and confirm RED**

Run: `python -m pytest tests/unit/test_polygon_historical_master_scripts.py -v`

Expected: collection fails because the audit script does not exist.

- [ ] **Step 3: Implement thin scripts and freeze protocol**

The acquisition script loops month ends, both activity states, then builds each monthly snapshot. It emits a secret-free JSON progress line after every month. The audit script calls the reconstruction validator first, reads only ticker columns from the external snapshots, and writes immutable reports. The protocol JSON copies every frozen requirement and records `execution_capability: FORBIDDEN`, `provider_splicing: FORBIDDEN`, and `paper_activation: false`.

- [ ] **Step 4: Run tests, protocol parse, and lint**

Run: `python -m pytest tests/unit/test_polygon_historical_master_scripts.py tests/unit/data/test_polygon_historical_master.py -v`

Expected: all tests pass.

Run: `python -m json.tool research/protocols/polygon_historical_master_v1.json > $null`

Expected: exit 0.

Run: `python -m ruff check scripts/acquire_polygon_historical_master.py scripts/audit_polygon_historical_master.py tests/unit/test_polygon_historical_master_scripts.py`

Expected: exit 0.

- [ ] **Step 5: Commit**

Commit: `git add scripts/acquire_polygon_historical_master.py scripts/audit_polygon_historical_master.py tests/unit/test_polygon_historical_master_scripts.py research/protocols/polygon_historical_master_v1.json && git commit -m "Add Polygon master acquisition commands"`

### Task 5: Evidence-gated integration with existing SIP audits

**Files:**
- Modify: `scripts/audit_us_market_sip_five_minute.py`
- Modify: `scripts/audit_us_market_sip_universe.py`
- Modify: `tests/unit/data/test_sip_five_minute_audit.py`
- Modify: `tests/unit/data/test_sip_universe_audit.py`

**Interfaces:**
- Both scripts require `--historical-master-validation PATH`.
- Produces: `_historical_master_validation(path: Path) -> dict[str, object]` that requires `passed is True`, exact namespace and date bounds, 99 months, zero partial files, valid hashes/page chains/reconstruction, and no validation rejection reasons.

- [ ] **Step 1: Add failing evidence-gate tests**

```python
def test_historical_master_gate_rejects_self_attestation(tmp_path: Path) -> None:
    path = tmp_path / "master.json"
    path.write_text('{"passed": true}', encoding="utf-8")
    with pytest.raises(RuntimeError, match="HISTORICAL_MASTER_VALIDATION_INCOMPLETE"):
        _historical_master_validation(path)

def test_historical_master_gate_accepts_complete_validator_evidence(tmp_path: Path) -> None:
    path = tmp_path / "master.json"
    path.write_text(json.dumps(complete_master_validation()), encoding="utf-8")
    assert _historical_master_validation(path)["months"] == 99
```

- [ ] **Step 2: Run focused tests and confirm RED**

Run: `python -m pytest tests/unit/data/test_sip_five_minute_audit.py tests/unit/data/test_sip_universe_audit.py -v`

Expected: failures identify the missing report loader and CLI argument.

- [ ] **Step 3: Implement report-gated integration**

Parse the immutable validator report, reject incomplete or mismatched evidence, and pass `historical_master_validated=True` only after the loader succeeds. Include the validation report hash and dataset namespace in each SIP audit result so the provenance remains traceable.

- [ ] **Step 4: Run focused tests and lint**

Run: `python -m pytest tests/unit/data/test_sip_five_minute_audit.py tests/unit/data/test_sip_universe_audit.py -v`

Expected: all tests pass.

Run: `python -m ruff check scripts/audit_us_market_sip_five_minute.py scripts/audit_us_market_sip_universe.py tests/unit/data/test_sip_five_minute_audit.py tests/unit/data/test_sip_universe_audit.py`

Expected: exit 0.

- [ ] **Step 5: Commit**

Commit: `git add scripts/audit_us_market_sip_five_minute.py scripts/audit_us_market_sip_universe.py tests/unit/data/test_sip_five_minute_audit.py tests/unit/data/test_sip_universe_audit.py && git commit -m "Gate SIP audits on Polygon master evidence"`

### Task 6: Live pilot, full acquisition, immutable audits, and final verification

**Files:**
- Create: external immutable artifacts under `E:/us-intraday-lab-data/us-market/data/staging/polygon_reference_tickers_v1/`
- Create: `research/results/2026-09-14-polygon-historical-master-audit.json`
- Create: `research/results/2026-09-14-polygon-historical-master-audit.md`
- Create new SIP audit result filenames rather than overwriting the existing failed audit evidence.

**Interfaces:**
- Uses the same acquisition and validator paths for pilot and full range.
- Produces a complete 99-month validation report or leaves the existing historical-master blocker intact.

- [ ] **Step 1: Run a one-month live pilot**

Run:

```powershell
$env:POLYGON_API_KEY=[Environment]::GetEnvironmentVariable('POLYGON_API_KEY','User')
python scripts/acquire_polygon_historical_master.py --root E:/us-intraday-lab-data/us-market --start 2018-01-01 --end 2018-01-31 --minimum-request-interval-seconds 0.75
```

Expected: one complete month, both activity states, no credential in output, and no `.tmp` files.

- [ ] **Step 2: Validate the pilot using the reconstruction validator**

Run the audit script for January 2018 to temporary result paths outside the repository and confirm `passed: true`. If it fails, preserve the evidence, add a failing unit test for the fault, and fix through a fresh RED-GREEN cycle.

- [ ] **Step 3: Run the full resume-safe acquisition**

Run:

```powershell
$env:POLYGON_API_KEY=[Environment]::GetEnvironmentVariable('POLYGON_API_KEY','User')
python scripts/acquire_polygon_historical_master.py --root E:/us-intraday-lab-data/us-market --start 2018-01-01 --end 2026-03-31 --minimum-request-interval-seconds 0.75
```

Expected: 99 canonical months and both activity-state page chains. Interrupted runs resume without rewriting verified pages.

- [ ] **Step 4: Write immutable full master and refreshed SIP audit evidence**

Run the Polygon audit with the frozen Alpaca asset snapshot and monthly decisions. Only if `passed: true`, run both SIP audits with `--historical-master-validation` and new output filenames. Existing failed reports remain untouched.

- [ ] **Step 5: Run full verification**

Run: `python -m pytest -q`

Expected: exit 0 with zero failures.

Run targeted Ruff on all changed Python files and `git diff --check`.

Expected: both exit 0.

- [ ] **Step 6: Inspect requirements and commit publishable evidence**

Verify the final report states exact month/page/row counts, hashes valid, reconstruction valid, partial files zero, unmatched symbols explicit, source splicing zero, and Paper activation false. Keep raw data untracked.

Commit: `git add research/protocols/polygon_historical_master_v1.json research/results/2026-09-14-polygon-historical-master-audit.json research/results/2026-09-14-polygon-historical-master-audit.md <new-sip-audit-result-files> && git commit -m "Validate independent historical security master"`

- [ ] **Step 7: Record stage conclusion**

Use project-local structured memory because MCP memory is unavailable. Record `summary`, `stage`, `kpi_version`, required project/market/frequency tags, exact validation outcome, and `next_step`. Do not call the strategy usable or activate Paper unless all independent research and execution-parity gates later pass.
