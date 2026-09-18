# SEC Beneficial-Ownership Training Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Normalize immutable 2021-2023 SEC Schedule 13D/13G metadata, build causal five-session ownership-disclosure features for the fixed 527-symbol coverage-limited sample, and run the preregistered 400-cell training screen.

**Architecture:** A focused data module reads only the already frozen canonical SEC submissions sources, verifies every source hash, normalizes exact qualifying forms through exact CIK identities, and projects them onto the frozen event cube with next-session availability. A separate feasibility module applies raw source/issuer/event coverage gates before delegating the fixed cost/delay grid to the established evaluator.

**Tech Stack:** Python 3.12, pandas, NumPy, JSON, parquet/pyarrow, pytest, Ruff, existing `us_intraday_lab` SEC and feasibility utilities.

## Global Constraints

- The sample is exactly 527 symbols from event SHA-256 `399020c0abbdd554e4f4652593debcf33a2090bcc684c5d78bc1e27da92889a9`; call it coverage-limited, never full market.
- Read only the canonical hashed SEC current responses and declared historical fragments; fetch no new source and infer no fragment, issuer, ownership direction, percentage, or reporting owner.
- Reuse 462 exact-matched symbols and preserve all 65 unmatched symbols.
- Qualifying forms are exactly `SC 13D`, `SC 13D/A`, `SC 13G`, and `SC 13G/A` during 2021-2023.
- Availability begins on the first sample session strictly after acceptance and lasts exactly five sample sessions; the cluster feature uses only the prior 20 sample sessions.
- Coverage requires complete source hashes, 300 unique CIK issuers with three filings, 7,000 symbol-filing events, and all three years.
- The grid is 5 families x 5 decision bars x 4 holding bars x 4 top counts = 400 cells, with 9 bp standard, 18 bp stress, and one-bar delayed-entry 9 bp stress.
- Do not load development or consumed periods, create strategy versions, touch Paper or pools, call broker/submit/cancel, enable order routing, or shut down the host.

---

### Task 1: Immutable Schedule 13D/13G normalization

**Files:**
- Create: `src/us_intraday_lab/data/sec_beneficial_ownership.py`
- Create: `scripts/build_sec_beneficial_ownership_training_snapshot.py`
- Create: `tests/unit/data/test_sec_beneficial_ownership.py`

**Interfaces:**
- Produces: `normalize_filings(responses: Iterable[tuple[str, int, dict]], identities: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]` and `build_snapshot(source_manifest: dict, identities: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]`.
- Normalized rows contain symbol, CIK, accession, filing/acceptance timestamps, exact form, source URL/hash, and four exact form flags.

- [ ] **Step 1: Write failing exact-form and duplicate tests**

```python
def test_normalizer_accepts_only_exact_schedule_forms():
    filings, rejected = normalize_filings(responses_with_13d_13g_and_13f(), identity_frame())
    assert set(filings["form"]) == {"SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A"}
    assert "13F-HR" not in set(filings["form"])

def test_conflicting_accession_fails_closed():
    with pytest.raises(ValueError, match="SEC_BENEFICIAL_ACCESSION_CONFLICT"):
        normalize_filings(conflicting_responses(), identity_frame())
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/unit/data/test_sec_beneficial_ownership.py -q`

Expected: collection failure because the module does not exist.

- [ ] **Step 3: Implement strict normalization and source verification**

Reuse the SEC parallel-array validator, parse official ISO timestamps, filter exact forms and training dates, deduplicate identical accessions, reject conflicts, preserve unmatched CIK rows, and expand shared CIKs only through explicit identity rows. The snapshot script reads every source listed in the canonical SEC 8-K v2 manifest, verifies path bytes against SHA-256 before parsing, reconstructs the CIK from the verified current response or exact fragment filename prefix, and atomically publishes snapshot, rejections, and a manifest that references every source hash.

- [ ] **Step 4: Run tests, lint, and commit**

Run: `python -m pytest tests/unit/data/test_sec_beneficial_ownership.py -q`

Run: `python -m ruff check src/us_intraday_lab/data/sec_beneficial_ownership.py scripts/build_sec_beneficial_ownership_training_snapshot.py tests/unit/data/test_sec_beneficial_ownership.py`

Commit: `git commit -m "Build SEC beneficial-ownership snapshot"`

### Task 2: Causal five-session features

**Files:**
- Modify: `src/us_intraday_lab/data/sec_beneficial_ownership.py`
- Create: `scripts/build_sec_beneficial_ownership_training_features.py`
- Modify: `tests/unit/data/test_sec_beneficial_ownership.py`

**Interfaces:**
- Produces: `build_event_features(events: pd.DataFrame, filings: pd.DataFrame, identities: pd.DataFrame) -> pd.DataFrame`.
- Output adds exact CIK, four form indicators, clustered-disclosure indicator, active accessions/count, latest acceptance, recency, raw filing count, and explicit coverage reason.

- [ ] **Step 1: Write failing availability and clustering tests**

```python
def test_state_starts_next_session_and_expires_after_five():
    result = build_event_features(seven_sessions(), one_13d(), identity_frame())
    assert result.loc[0, "coverage_reason"] == "SEC_BENEFICIAL_NO_ACTIVE_FILING"
    assert result.loc[1:5, "sec_beneficial_sc13d"].eq(1).all()
    assert result.loc[6, "coverage_reason"] == "SEC_BENEFICIAL_NO_ACTIVE_FILING"

def test_cluster_uses_only_prior_twenty_sessions():
    result = build_event_features(twenty_two_sessions(), two_prior_filings(), identity_frame())
    assert result.loc[result["session_date"].eq(target_session), "sec_beneficial_clustered"].iat[0] == 1
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/unit/data/test_sec_beneficial_ownership.py -q`

Expected: failure because causal feature projection does not exist.

- [ ] **Step 3: Implement causal projection**

Map each filing to the first strictly later sample session, activate five sessions, aggregate overlapping forms, and compute the cluster flag from filing availability sessions in the previous 20-session window including the current availability session but never future sessions. Preserve raw inventory before projection and map exact CIK from the frozen identity table.

- [ ] **Step 4: Run tests, lint, and commit**

Run: `python -m pytest tests/unit/data/test_sec_beneficial_ownership.py -q`

Run: `python -m ruff check src/us_intraday_lab/data/sec_beneficial_ownership.py scripts/build_sec_beneficial_ownership_training_features.py tests/unit/data/test_sec_beneficial_ownership.py`

Commit: `git commit -m "Build causal SEC ownership features"`

### Task 3: Frozen coverage and 400-cell diagnostic

**Files:**
- Create: `src/us_intraday_lab/sec_beneficial_ownership_feasibility.py`
- Create: `scripts/diagnose_sec_beneficial_ownership_training.py`
- Create: `tests/unit/test_sec_beneficial_ownership_feasibility.py`

**Interfaces:**
- Produces: `coverage_gate(features: pd.DataFrame, manifest: dict) -> dict[str, object]`, `specifications() -> tuple[Specification, ...]`, and `run_diagnostic(...) -> tuple[pd.DataFrame, dict[str, object]]`.

- [ ] **Step 1: Write failing coverage and grid tests**

```python
def test_gate_requires_sources_300_issuers_7000_events_and_three_years():
    assert coverage_gate(inventory(300, 24), complete_manifest())["passed"] is True
    assert coverage_gate(inventory(299, 24), complete_manifest())["passed"] is False
    assert coverage_gate(inventory(300, 23), complete_manifest())["passed"] is False
    assert coverage_gate(inventory(300, 24), incomplete_manifest())["passed"] is False

def test_grid_has_exactly_400_unique_cells():
    assert len(specifications()) == len(set(specifications())) == 400
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/unit/test_sec_beneficial_ownership_feasibility.py -q`

Expected: collection failure because the feasibility module does not exist.

- [ ] **Step 3: Implement fail-closed diagnostic**

Define five continuation families and 400 specifications. Validate event, source-manifest, snapshot, and feature hashes. Apply coverage before returns. Delegate standard/stress/delay evaluation to the established evaluator with terminal decisions `ACQUIRE_DEVELOPMENT_SEC_BENEFICIAL_OWNERSHIP` and `ABANDON_SEC_BENEFICIAL_OWNERSHIP_NO_VERSION_CREATED`. Every summary keeps later data false, versions zero, Paper false, and route forbidden.

- [ ] **Step 4: Run tests, lint, and commit**

Run: `python -m pytest tests/unit/test_sec_beneficial_ownership_feasibility.py -q`

Run: `python -m ruff check src/us_intraday_lab/sec_beneficial_ownership_feasibility.py scripts/diagnose_sec_beneficial_ownership_training.py tests/unit/test_sec_beneficial_ownership_feasibility.py`

Commit: `git commit -m "Implement SEC ownership feasibility diagnostic"`

### Task 4: Execute, verify, and freeze the result

**Files:**
- Create: `research/results/2026-09-19-sec-beneficial-ownership-training-feasibility-summary.json`
- Create: `research/results/2026-09-19-sec-beneficial-ownership-training-feasibility-summary.md`
- Create: `memory/2026-09-19-sec-beneficial-ownership-training-local.md`

**Interfaces:**
- Produces immutable external snapshot/features/cells, tracked terminal evidence, and structured fallback memory.

- [ ] **Step 1: Build and hash the source snapshot**

Run the snapshot script against the canonical SEC 8-K v2 manifest. Require all listed source hashes to match, 65 unmatched symbols, exact forms only, and no filing after 2023-12-31.

- [ ] **Step 2: Apply coverage before returns**

If source completeness, 300 unique qualifying CIKs, 7,000 symbol events, or three-year coverage fails, emit the coverage-abandon decision, skip cells, persist evidence, and move later to a different source.

- [ ] **Step 3: Build features and run exactly 400 cells after coverage passes**

Require exact artifact hashes, `status == "COMPLETE"`, and `cells_completed == 400`; do not load later periods.

- [ ] **Step 4: Verify and freeze evidence**

Run focused tests, targeted Ruff, `git diff --check`, and `python -m pytest -q`. Record existing unrelated baseline failures rather than modifying them. Write fallback memory with `summary`, `stage`, `kpi_version`, required tags, and `next_step`.

- [ ] **Step 5: Commit and push**

Commit only publishable code, tests, summaries, and memory. Keep raw responses, parquet caches, manifests, logs, and `state/` untracked. Push `codex/v550-v649-second-strategy`.
