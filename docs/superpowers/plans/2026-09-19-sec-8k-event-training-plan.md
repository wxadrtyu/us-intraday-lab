# SEC 8-K Structured-Event Training Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Acquire complete immutable 2021-2023 SEC submissions history, build causal structured 8-K category features for the fixed 527-symbol coverage-limited sample, and run the preregistered 400-cell training screen.

**Architecture:** A focused data module validates current and declared historical SEC submission responses, normalizes original 8-K item metadata, and projects exact-CIK filing states onto the frozen event cube beginning on the next sample session. Thin scripts manage immutable/resumable acquisition, feature publication, and a versionless diagnostic that separates raw filing coverage from event-row coverage and reuses the established cost/delay evaluator.

**Tech Stack:** Python 3.12, pandas, NumPy, urllib, JSON, parquet/pyarrow, pytest, Ruff, existing `us_intraday_lab` feasibility utilities.

## Global Constraints

- The sample is exactly the 527 symbols in event SHA-256 `399020c0abbdd554e4f4652593debcf33a2090bcc684c5d78bc1e27da92889a9` and must be called coverage-limited, never full market.
- Use only official SEC current submissions and exact historical fragment names declared by those responses; requests are sequential and no faster than four per second.
- Reuse the frozen exact identity snapshot with 462 matched symbols and 65 preserved unmatched symbols; never guess tickers or issuer identities.
- Only original `8-K` filings create signals; `8-K/A`, blank/unknown items, malformed rows, and conflicts remain explicit audit evidence.
- Availability begins on the first sample session strictly after the acceptance calendar date and lasts exactly three sample sessions.
- The coverage gate requires at least 300 exact-mapped issuers with three categorized filings, at least 5,000 categorized symbol-filing events, all three training years, and every required immutable source record.
- The frozen grid is 5 categories x 5 decision bars x 4 holding bars x 4 top counts = 400 cells, with 9 bp standard, 18 bp stress, and one-bar delayed entry at 9 bp.
- Do not load development or consumed periods, create strategy versions, touch Paper or pools, call broker/submit/cancel, enable order routing, or shut down the host.

---

### Task 1: SEC submissions and 8-K normalization contract

**Files:**
- Create: `src/us_intraday_lab/data/sec_8k_events.py`
- Create: `tests/unit/data/test_sec_8k_events.py`

**Interfaces:**
- Produces: `validate_submission_response(payload: dict, source: str) -> None`, `select_training_fragments(payload: dict, start: date, end: date) -> tuple[str, ...]`, `normalize_8k_filings(responses: Iterable[tuple[str, dict]], identities: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]`, and `parse_items(value: object) -> tuple[str, ...]`.
- Normalized rows are exact `(symbol, accession_number)` records with CIK, acceptance timestamp, filing/report dates, size, exact item tuple, five frozen category flags, source URL, and provenance status.

- [ ] **Step 1: Write failing schema, fragment, and item tests**

```python
def test_fragment_selection_uses_only_declared_intersections():
    payload = submission_payload(files=[
        {"name": "old.json", "filingFrom": "2018-01-01", "filingTo": "2020-12-31"},
        {"name": "train.json", "filingFrom": "2021-01-01", "filingTo": "2022-06-30"},
    ])
    assert select_training_fragments(payload, date(2021, 1, 1), date(2023, 12, 31)) == ("train.json",)

def test_item_parser_is_exact_and_deduplicated():
    assert parse_items("2.02, 9.01,2.02") == ("2.02", "9.01")
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/unit/data/test_sec_8k_events.py -q`

Expected: collection failure because `us_intraday_lab.data.sec_8k_events` does not exist.

- [ ] **Step 3: Implement strict validation and normalization**

Validate equal lengths for `accessionNumber`, `filingDate`, `reportDate`, `acceptanceDateTime`, `form`, `items`, `size`, and `primaryDocument`. Select only declared fragments intersecting the training interval. Parse comma-delimited items exactly, classify only items `2.02`, `1.01`, `2.01`, `5.02`, and `8.01`, reject conflicting duplicate accessions, preserve identical duplicates as audit rows, and duplicate shared-CIK filings only through explicit frozen identity rows.

- [ ] **Step 4: Add edge-case tests and run GREEN**

Add tests for unequal arrays, malformed ranges/timestamps, current plus historical deduplication, amendments, blank/unknown items, exact CIK matching, unmatched CIKs, and shared CIKs.

Run: `python -m pytest tests/unit/data/test_sec_8k_events.py -q`

Expected: all tests pass.

- [ ] **Step 5: Lint and commit**

Run: `python -m ruff check src/us_intraday_lab/data/sec_8k_events.py tests/unit/data/test_sec_8k_events.py`

Commit: `git commit -m "Implement SEC 8-K data contract"`

### Task 2: Immutable current and historical acquisition

**Files:**
- Create: `scripts/acquire_sec_8k_event_training.py`
- Create: `tests/unit/test_acquire_sec_8k_event_training.py`

**Interfaces:**
- Consumes the frozen current-submissions directory, its hash evidence, and Task 1 validation/fragment functions.
- Produces immutable required historical fragments, `sec_8k_event_training_v1.parquet`, `rejections.parquet`, and `manifest.json` under `E:/us-intraday-lab-data/us-market/data/staging/sec_8k_event_training_v1/`.

- [ ] **Step 1: Write failing immutable-resume tests**

```python
def test_acquisition_reuses_verified_current_and_historical_bytes(tmp_path):
    first = acquire_training_snapshot(fetch=fake_fetch, root=tmp_path, identities=identity_frame())
    second = acquire_training_snapshot(fetch=forbidden_fetch, root=tmp_path, identities=identity_frame())
    assert second["snapshot_sha256"] == first["snapshot_sha256"]

def test_acquisition_refuses_fragment_collision(tmp_path):
    acquire_training_snapshot(fetch=fake_fetch, root=tmp_path, identities=identity_frame())
    corrupt_one_fragment(tmp_path)
    with pytest.raises(RuntimeError, match="SEC_8K_RAW_IMMUTABLE_COLLISION"):
        acquire_training_snapshot(fetch=fake_fetch, root=tmp_path, identities=identity_frame())
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/unit/test_acquire_sec_8k_event_training.py -q`

Expected: import failure for the missing acquisition script.

- [ ] **Step 3: Implement sequential fail-closed acquisition**

Verify every reused current response against frozen SHA-256 evidence, derive exact required fragment names, and request only missing declared URLs with a declared SEC user agent, 0.25-second minimum interval, bounded 429/5xx/transport retries, temporary files, atomic rename, and SHA-256 resume validation. Publish normalized/rejection parquet only after all required responses validate. Record URLs, retrieval times, bytes, hashes, schema counts, duplicate status, 462/65 identity counts, filing/event counts, years, and no-execution invariants.

- [ ] **Step 4: Run focused tests, lint, and commit**

Run: `python -m pytest tests/unit/test_acquire_sec_8k_event_training.py tests/unit/data/test_sec_8k_events.py -q`

Run: `python -m ruff check scripts/acquire_sec_8k_event_training.py tests/unit/test_acquire_sec_8k_event_training.py`

Commit: `git commit -m "Acquire immutable SEC 8-K training data"`

### Task 3: Causal three-session event features

**Files:**
- Modify: `src/us_intraday_lab/data/sec_8k_events.py`
- Create: `scripts/build_sec_8k_event_training_features.py`
- Modify: `tests/unit/data/test_sec_8k_events.py`

**Interfaces:**
- Produces: `build_event_features(events: pd.DataFrame, filings: pd.DataFrame, identities: pd.DataFrame) -> pd.DataFrame`.
- Output preserves each training event key and adds five category indicators, active accessions, latest acceptance timestamp, active filing/item counts, `log1p(size)`, days since latest acceptance, raw categorized filing count, and explicit coverage reason.

- [ ] **Step 1: Write failing causality and inventory tests**

```python
def test_state_starts_strictly_next_session_and_expires_after_three():
    result = build_event_features(five_sessions(), one_accepted_filing(), identity_frame())
    assert result.loc[0, "coverage_reason"] == "SEC_8K_NO_ACTIVE_FILING"
    assert result.loc[1:3, "sec_8k_earnings_results"].eq(1).all()
    assert result.loc[4, "coverage_reason"] == "SEC_8K_NO_ACTIVE_FILING"

def test_raw_inventory_is_not_lost_during_projection():
    result = build_event_features(one_event_row(), three_distinct_filings(), identity_frame())
    assert result.loc[0, "sec_8k_categorized_filing_count"] == 3
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/unit/data/test_sec_8k_events.py -q`

Expected: failures because `build_event_features` and inventory fields do not exist.

- [ ] **Step 3: Implement causal projection**

Map each accepted filing to the first event session whose date is strictly later than its acceptance date, activate exactly three sample sessions, aggregate overlapping filings without backdating, retain multi-category membership, and preserve missingness. Compute raw issuer and symbol filing inventories before event projection. Never use same-day clock assumptions or document text.

- [ ] **Step 4: Run tests, lint, and commit**

Run: `python -m pytest tests/unit/data/test_sec_8k_events.py -q`

Run: `python -m ruff check src/us_intraday_lab/data/sec_8k_events.py scripts/build_sec_8k_event_training_features.py tests/unit/data/test_sec_8k_events.py`

Commit: `git commit -m "Build causal SEC 8-K features"`

### Task 4: Frozen coverage gate and 400-cell diagnostic

**Files:**
- Create: `src/us_intraday_lab/sec_8k_event_feasibility.py`
- Create: `scripts/diagnose_sec_8k_event_training.py`
- Create: `tests/unit/test_sec_8k_event_feasibility.py`

**Interfaces:**
- Produces: `coverage_gate(features: pd.DataFrame, manifest: dict) -> dict[str, object]`, `specifications() -> tuple[Specification, ...]`, and `run_diagnostic(...) -> tuple[pd.DataFrame, dict[str, object]]`.
- Reuses the established evaluator for standard, 18 bp, and delayed scenarios.

- [ ] **Step 1: Write failing gate and grid tests**

```python
def test_coverage_requires_300_issuers_5000_events_and_complete_sources():
    assert coverage_gate(inventory_frame(300, 5000), complete_manifest())["passed"] is True
    assert coverage_gate(inventory_frame(299, 6000), complete_manifest())["passed"] is False
    assert coverage_gate(inventory_frame(300, 4999), complete_manifest())["passed"] is False
    assert coverage_gate(inventory_frame(300, 5000), incomplete_manifest())["passed"] is False

def test_grid_has_exactly_400_unique_cells():
    grid = specifications()
    assert len(grid) == len(set(grid)) == 400
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/unit/test_sec_8k_event_feasibility.py -q`

Expected: import failure for the missing feasibility module.

- [ ] **Step 3: Implement the fail-closed screen**

Define the five frozen category families and 400 specifications. Validate exact event, snapshot, rejection, and feature hashes. Apply source completeness and raw coverage gates before return evaluation. Reuse the established evaluator with terminal decisions `ACQUIRE_DEVELOPMENT_SEC_8K_EVENT` and `ABANDON_SEC_8K_EVENT_NO_VERSION_CREATED`. Every summary records `development_or_consumed_loaded=false`, `strategy_versions_created=0`, `paper_activation=false`, and `order_route="FORBIDDEN"`.

- [ ] **Step 4: Run tests, lint, and commit**

Run: `python -m pytest tests/unit/test_sec_8k_event_feasibility.py -q`

Run: `python -m ruff check src/us_intraday_lab/sec_8k_event_feasibility.py scripts/diagnose_sec_8k_event_training.py tests/unit/test_sec_8k_event_feasibility.py`

Commit: `git commit -m "Implement SEC 8-K feasibility diagnostic"`

### Task 5: Execute and freeze the terminal training result

**Files:**
- Create: `research/results/2026-09-19-sec-8k-event-training-feasibility-summary.json`
- Create: `research/results/2026-09-19-sec-8k-event-training-feasibility-summary.md`
- Create: `memory/2026-09-19-sec-8k-event-training-local.md`

**Interfaces:**
- Consumes the frozen event cube, frozen SEC identity/current-submission evidence, and Tasks 1-4.
- Produces immutable external source/feature/cell artifacts, tracked terminal evidence, and structured local fallback memory.

- [ ] **Step 1: Run immutable acquisition**

Run the module-form acquisition command against the external staging root. Require a `COMPLETE` manifest, exact hashes for every reused/downloaded response, 65 unmatched symbols, no filing after 2023-12-31, and no undeclared fragment.

- [ ] **Step 2: Apply the preregistered coverage gate**

If any required source is missing, fewer than 300 issuers have three categorized filings, fewer than 5,000 categorized symbol-filing events exist, or a training year is absent, write `ABANDON_SEC_8K_EVENT_COVERAGE_GATE`, skip the grid, persist evidence, commit, push, and proceed later to a genuinely different source.

- [ ] **Step 3: Build features and run exactly 400 cells only after coverage passes**

Hash the feature cache, run the diagnostic with exact expected hashes, and require `status == "COMPLETE"` and `cells_completed == 400`. Do not open development or consumed data.

- [ ] **Step 4: Verify all evidence and repository invariants**

Run focused tests, targeted Ruff, `git diff --check`, and `python -m pytest -q`. Assert tracked summary hashes match external files, retained family counts match cell results, all required scenarios completed, and every no-execution flag remains intact. Report pre-existing unrelated baseline failures without repairing them in this line.

- [ ] **Step 5: Save fallback memory, commit, and push**

Write `summary`, `stage`, `kpi_version`, `tags`, and `next_step`; tags include `project:quant-agent-team`, `market:cn_a`, and `freq:daily`. Commit only publishable code, tests, summaries, and memory. Keep raw responses, parquet caches, manifests, logs, and `state/` untracked. Push `codex/v550-v649-second-strategy`.
