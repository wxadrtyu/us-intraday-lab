# SEC Form 4 Insider-Flow Training Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Acquire immutable 2021-2023 SEC Form 4 bulk data, build causal insider-flow features for the fixed 527-symbol coverage-limited sample, and run the preregistered 400-cell training feasibility diagnostic.

**Architecture:** A focused data module validates and normalizes official quarterly Form 3/4/5 ZIP tables, derives exact-CIK original-Form-4 P/S filing aggregates, and projects those aggregates onto the existing frozen event cube with next-session availability and five-session expiry. Thin scripts perform immutable acquisition, feature publication, and a versionless diagnostic that reuses the established cost/delay evaluator while keeping raw filing coverage separate from event-row signal coverage.

**Tech Stack:** Python 3.12, pandas, NumPy, urllib, zipfile, parquet/pyarrow, pytest, Ruff, existing `us_intraday_lab` feasibility utilities.

## Global Constraints

- The sample is exactly the 527 symbols in event SHA-256 `399020c0abbdd554e4f4652593debcf33a2090bcc684c5d78bc1e27da92889a9` and must be called coverage-limited, never full market.
- Acquire only official 2021 Q1 through 2023 Q4 SEC `YYYYqQ_form345.zip` files, sequentially at no more than four requests per second.
- Reuse the frozen exact SEC identity snapshot: 462 matched symbols and 65 preserved unmatched symbols; never guess tickers or ETF identities.
- Signals use only original Form 4 non-derivative P/S transactions with internally consistent direction, positive finite shares and price, and no equity-swap flag.
- Availability begins on the first event session strictly after filing date and expires after five event sessions.
- The coverage gate is at least 300 issuers with at least three qualifying filings and at least 3,000 total qualifying issuer-filing events across all three years.
- The frozen grid is 5 families x 5 decision bars x 4 holding bars x 4 top counts = 400 cells, with 9 bp standard, 18 bp stress, and one-bar delayed-entry 9 bp stress.
- Do not load development or consumed periods, create strategy versions, touch Paper or pools, call broker/submit/cancel, enable an order route, or shut down the host.

---

### Task 1: Official ZIP and table contract

**Files:**
- Create: `src/us_intraday_lab/data/sec_form4_insider_flow.py`
- Create: `tests/unit/data/test_sec_form4_insider_flow.py`

**Interfaces:**
- Produces: `quarter_urls() -> tuple[str, ...]`, `parse_quarter_zip(body: bytes, source: str) -> dict[str, pd.DataFrame]`, and `normalize_form4_filings(tables: dict[str, pd.DataFrame], identities: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]`.
- The normalized filing frame has one row per exact `(symbol, accession)` with filing date, purchase/sale notionals, net balance, purchaser count, officer/director share, holding fraction, lag, and provenance counts.

- [ ] **Step 1: Write failing contract tests**

```python
def test_quarter_urls_are_exactly_2021_through_2023():
    urls = quarter_urls()
    assert len(urls) == 12
    assert urls[0].endswith("2021q1_form345.zip")
    assert urls[-1].endswith("2023q4_form345.zip")

def test_normalizer_accepts_only_consistent_original_form4_ps_rows():
    tables = synthetic_tables(document_type="4", code="P", direction="A")
    filings, rejected = normalize_form4_filings(tables, identity_frame())
    assert filings.loc[0, "purchase_notional"] == 5000.0
    assert rejected.empty
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/unit/data/test_sec_form4_insider_flow.py -q`

Expected: collection failure because `us_intraday_lab.data.sec_form4_insider_flow` does not exist.

- [ ] **Step 3: Implement strict parsing and normalization**

Implement documented tab-delimited table membership and keys for `SUBMISSION.tsv`, `REPORTINGOWNER.tsv`, and `NONDERIV_TRANS.tsv`. Reject duplicate primary keys, missing foreign accessions, amendments, Forms 3/5, direction mismatches, nonpositive or nonnumeric shares/prices, future transaction dates, and equity swaps. Aggregate transaction rows by accession and then duplicate the issuer filing only across explicitly frozen shared-CIK symbol mappings.

- [ ] **Step 4: Add edge-case tests and run GREEN**

Add tests for malformed ZIPs, duplicate keys, broken foreign keys, amendments, late rows, missing price, equity swap, exact CIK match, unmatched CIK, and shared CIKs.

Run: `python -m pytest tests/unit/data/test_sec_form4_insider_flow.py -q`

Expected: all tests pass.

- [ ] **Step 5: Lint and commit**

Run: `python -m ruff check src/us_intraday_lab/data/sec_form4_insider_flow.py tests/unit/data/test_sec_form4_insider_flow.py`

Commit: `git commit -m "Implement SEC Form 4 data contract"`

### Task 2: Immutable training acquisition

**Files:**
- Create: `scripts/acquire_sec_form4_insider_flow_training.py`
- Create: `tests/unit/test_acquire_sec_form4_insider_flow_training.py`

**Interfaces:**
- Consumes: `quarter_urls()` and `parse_quarter_zip()` from Task 1 plus the frozen SEC identity JSON.
- Produces: 12 immutable raw ZIPs, `sec_form4_insider_flow_training_v1.parquet`, `rejections.parquet`, and `manifest.json` under `E:/us-intraday-lab-data/us-market/data/staging/sec_form4_insider_flow_training_v1/`.

- [ ] **Step 1: Write failing acquisition tests**

```python
def test_acquisition_resumes_identical_raw_bytes(tmp_path):
    first = acquire_training_snapshot(fetch=fake_fetch, root=tmp_path, identities=identity_frame())
    second = acquire_training_snapshot(fetch=forbidden_fetch, root=tmp_path, identities=identity_frame())
    assert second[1] == first[1]

def test_acquisition_refuses_immutable_collision(tmp_path):
    acquire_training_snapshot(fetch=fake_fetch, root=tmp_path, identities=identity_frame())
    corrupt_first_zip(tmp_path)
    with pytest.raises(RuntimeError, match="SEC_FORM4_RAW_IMMUTABLE_COLLISION"):
        acquire_training_snapshot(fetch=fake_fetch, root=tmp_path, identities=identity_frame())
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/unit/test_acquire_sec_form4_insider_flow_training.py -q`

Expected: import failure for the missing acquisition script.

- [ ] **Step 3: Implement resumable sequential acquisition**

Use a declared SEC user agent, sequential requests, a 0.25-second minimum request interval, bounded retry for 429/5xx/transport errors, temporary files plus atomic rename, and SHA-256 validation on every resume. Build normalized and rejection frames only after all 12 ZIPs validate. The manifest records URL, headers, retrieval time, bytes, SHA-256, table row counts, matched/unmatched identities, normalized filings, rejection counts, and the training-only/no-order invariants.

- [ ] **Step 4: Run tests, lint, and commit**

Run: `python -m pytest tests/unit/test_acquire_sec_form4_insider_flow_training.py tests/unit/data/test_sec_form4_insider_flow.py -q`

Run: `python -m ruff check scripts/acquire_sec_form4_insider_flow_training.py tests/unit/test_acquire_sec_form4_insider_flow_training.py`

Commit: `git commit -m "Acquire immutable SEC Form 4 training data"`

### Task 3: Causal event features and raw coverage inventory

**Files:**
- Modify: `src/us_intraday_lab/data/sec_form4_insider_flow.py`
- Create: `scripts/build_sec_form4_insider_flow_training_features.py`
- Modify: `tests/unit/data/test_sec_form4_insider_flow.py`

**Interfaces:**
- Produces: `build_event_features(events: pd.DataFrame, filings: pd.DataFrame, identities: pd.DataFrame) -> pd.DataFrame`.
- Output preserves every training event key and adds five ranked feature columns, `sec_form4_qualifying_filing_count`, active accessions, filing date, and an explicit coverage reason.

- [ ] **Step 1: Write failing causality tests**

```python
def test_form4_state_starts_next_session_and_expires_after_five():
    result = build_event_features(seven_sessions(), one_purchase_filing(), identity_frame())
    assert result.loc[0, "coverage_reason"] == "SEC_FORM4_NO_ACTIVE_FILING"
    assert result.loc[1:5, "coverage_reason"].eq("COVERED").all()
    assert result.loc[6, "coverage_reason"] == "SEC_FORM4_NO_ACTIVE_FILING"

def test_raw_inventory_survives_event_projection():
    result = build_event_features(one_event_row(), four_distinct_filings(), identity_frame())
    assert result.loc[0, "sec_form4_qualifying_filing_count"] == 4
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/unit/data/test_sec_form4_insider_flow.py -q`

Expected: failures because `build_event_features` and the inventory column do not exist.

- [ ] **Step 3: Implement causal projection**

Filter event sessions to 2021-01-01 through 2023-12-31, map every filing to the first strictly later session, activate exactly five sessions, aggregate overlapping active filings without backdating, rank finite feature values by session, and preserve missingness. Compute issuer coverage counts from the normalized filing inventory before projecting onto event rows and map the immutable count onto every row for that symbol.

- [ ] **Step 4: Run focused tests, lint, and commit**

Run: `python -m pytest tests/unit/data/test_sec_form4_insider_flow.py -q`

Run: `python -m ruff check src/us_intraday_lab/data/sec_form4_insider_flow.py scripts/build_sec_form4_insider_flow_training_features.py tests/unit/data/test_sec_form4_insider_flow.py`

Commit: `git commit -m "Build causal SEC Form 4 features"`

### Task 4: Frozen coverage and 400-cell diagnostic

**Files:**
- Create: `src/us_intraday_lab/sec_form4_insider_flow_feasibility.py`
- Create: `scripts/diagnose_sec_form4_insider_flow_training.py`
- Create: `tests/unit/test_sec_form4_insider_flow_feasibility.py`

**Interfaces:**
- Produces: `coverage_gate(features: pd.DataFrame) -> dict[str, object]`, `specifications() -> tuple[Specification, ...]`, and `run_diagnostic(...) -> tuple[pd.DataFrame, dict[str, object]]`.
- Reuses the existing configured feasibility evaluator for standard, cost, and delay scenarios.

- [ ] **Step 1: Write failing gate and grid tests**

```python
def test_coverage_requires_300_issuers_and_3000_filings():
    passed = coverage_gate(inventory_frame(issuers=300, filings=10))
    assert passed["passed"] is True
    assert coverage_gate(inventory_frame(issuers=299, filings=11))["passed"] is False
    assert coverage_gate(inventory_frame(issuers=300, filings=9))["passed"] is False

def test_grid_has_exactly_400_unique_cells():
    grid = specifications()
    assert len(grid) == len(set(grid)) == 400
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/unit/test_sec_form4_insider_flow_feasibility.py -q`

Expected: import failure for the missing feasibility module.

- [ ] **Step 3: Implement fail-closed diagnostic**

Define the five frozen families and 400 specifications. Validate exact event and feature hashes. Apply the raw issuer inventory gate before return computation. Reuse the established evaluator with decisions `ACQUIRE_DEVELOPMENT_SEC_FORM4_INSIDER_FLOW` and `ABANDON_SEC_FORM4_INSIDER_FLOW_NO_VERSION_CREATED`. Every summary records `development_or_consumed_loaded=false`, `strategy_versions_created=0`, `paper_activation=false`, and `order_route="FORBIDDEN"`.

- [ ] **Step 4: Run tests, lint, and commit**

Run: `python -m pytest tests/unit/test_sec_form4_insider_flow_feasibility.py -q`

Run: `python -m ruff check src/us_intraday_lab/sec_form4_insider_flow_feasibility.py scripts/diagnose_sec_form4_insider_flow_training.py tests/unit/test_sec_form4_insider_flow_feasibility.py`

Commit: `git commit -m "Implement SEC Form 4 feasibility diagnostic"`

### Task 5: Execute acquisition and terminal training screen

**Files:**
- Create: `research/results/2026-09-19-sec-form4-insider-flow-training-feasibility-summary.json`
- Create: `research/results/2026-09-19-sec-form4-insider-flow-training-feasibility-summary.md`
- Create: `memory/2026-09-19-sec-form4-insider-flow-training-local.md`

**Interfaces:**
- Consumes the frozen event cube, the prior frozen SEC identity snapshot, and Tasks 1-4.
- Produces the immutable external snapshot, feature cache, 400-cell result when coverage passes, tracked summary, and local fallback memory.

- [ ] **Step 1: Run the 12-quarter acquisition**

Run the module-form acquisition command against the external staging root. Confirm the manifest is `COMPLETE`, lists exactly 12 source ZIP hashes, preserves 65 unmatched symbols, and loads no date after 2023-12-31.

- [ ] **Step 2: Apply the preregistered coverage gate**

If fewer than 300 issuers have three qualifying original Form 4 filings or fewer than 3,000 filings qualify, write the immutable coverage rejection, skip the grid, write fallback memory, commit, push, and move to a genuinely different preregistered source.

- [ ] **Step 3: Build features and run 400 cells only if coverage passes**

Hash the feature cache, run the diagnostic with exact expected hashes, and require `status == "COMPLETE"` and `cells_completed == 400`. Do not open development or consumed data.

- [ ] **Step 4: Verify repository and artifact invariants**

Run focused tests, targeted Ruff, `git diff --check`, and `python -m pytest -q`. Assert summary hashes match external files, retained family counts match the cells, and all no-execution flags are intact. Existing unrelated baseline failures must be reported rather than repaired in this line.

- [ ] **Step 5: Freeze memory, commit, and push**

Write structured local fallback memory with `summary`, `stage`, `kpi_version`, `tags`, and `next_step`; tags include `project:quant-agent-team`, `market:cn_a`, and `freq:daily`. Commit only publishable code, tests, summaries, and memory; leave raw ZIPs, caches, manifests, logs, and `state/` untracked. Push `codex/v550-v649-second-strategy`.
