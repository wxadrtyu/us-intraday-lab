# USPTO Patent-Grant Training Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Acquire two immutable USPTO-authored PatentsView archives, build strict one-to-one issuer-mapped causal patent-grant features for the fixed 527-symbol training sample, and run the preregistered 400-cell feasibility screen only after coverage passes.

**Architecture:** A focused patent data module verifies the publisher archive hashes, streams the patent and raw assignee tables, applies a frozen one-to-one issuer-name contract, and publishes an immutable normalized snapshot with every exclusion preserved. A causal feature builder projects public grant batches onto the first strictly later sample session for five sessions. A separate feasibility module applies source and mapping coverage gates before delegating the fixed cost/delay grid to the established evaluator.

**Tech Stack:** Python 3.12, pandas, NumPy, ZIP/TSV streaming, Unicode normalization, hashlib, parquet/pyarrow, pytest, Ruff, existing `us_intraday_lab` feasibility utilities.

## Global Constraints

- The sample is exactly 527 symbols from event SHA-256 `399020c0abbdd554e4f4652593debcf33a2090bcc684c5d78bc1e27da92889a9`; call it coverage-limited, never full market.
- Read only Zenodo record `15058362` files `g_patent.tsv.zip` and `g_assignee_not_disambiguated.tsv.zip`; do not log in, create a USPTO account/API key, substitute mirrors, or fetch unrelated tables.
- Require publisher MD5 values `f74fbde4b2adbf980b8e4ed5394f16d2` and `6154c6d989206de65b1367b886f744d3`; also record byte counts and local SHA-256.
- Use only raw assignee organization names and the frozen mechanical one-to-one SEC-title mapping. No fuzzy matches, aliases, subsidiaries, acronyms, translations, manual overrides, or model-derived assignee identity.
- Preserve the existing 65 SEC-unmatched symbols and every additional collision or unmatched patent assignee.
- Availability begins on the first sample session strictly after grant date and lasts exactly five sample sessions; all trailing features are causal.
- Coverage requires complete hashes, 100 uniquely mapped issuers with three patents, 5,000 symbol-patent events, and all three training years before returns.
- The grid is 5 families x 5 decision bars x 4 holding bars x 4 top counts = 400 cells, with 9 bp standard, 18 bp stress, and one-bar delayed-entry 9 bp stress.
- Do not load development or consumed periods, create strategy versions, touch Paper or pools, call broker/submit/cancel, enable order routing, or shut down the host.

---

### Task 1: Immutable archives and strict issuer mapping

**Files:**
- Create: `src/us_intraday_lab/data/uspto_patent_grants.py`
- Create: `scripts/build_uspto_patent_grant_training_snapshot.py`
- Create: `tests/unit/data/test_uspto_patent_grants.py`

**Interfaces:**
- Produces: `canonicalize_organization(name: str) -> str`.
- Produces: `build_issuer_map(sec_identities: pd.DataFrame, assignees: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]`.
- Produces: `normalize_grants(patents: Iterable[pd.DataFrame], assignees: Iterable[pd.DataFrame], issuer_map: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]`.
- The snapshot script verifies both archive hashes before parsing and atomically writes grants, mapping audit, rejections, and a manifest.

- [ ] **Step 1: Write failing canonicalization and ambiguity tests**

```python
def test_canonicalization_is_mechanical_and_suffix_limited():
    assert canonicalize_organization("Acme, Inc.") == "ACME"
    assert canonicalize_organization("A.C.M.E. Holdings") == "A C M E HOLDINGS"

def test_mapping_accepts_only_unique_keys_and_preserves_ambiguity():
    mapping, rejected = build_issuer_map(sec_titles(), raw_assignees())
    assert mapping.loc[mapping["symbol"].eq("AAA"), "raw_assignee_name"].iat[0] == "Acme Inc"
    assert "USPTO_ASSIGNEE_KEY_AMBIGUOUS" in set(rejected["reason"])
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/unit/data/test_uspto_patent_grants.py -q`

Expected: collection failure because `uspto_patent_grants` does not exist.

- [ ] **Step 3: Implement archive verification, chunked parsing, and normalization**

Implement the exact canonicalization and one-to-one key checks from the spec.
Reject blank names, non-organization rows, collisions on either side, invalid
dates, patent joins without exactly one matching patent row, and conflicting
duplicate patent metadata. Filter dates only after source validation. Parse the
ZIP members in chunks and retain only columns needed by the data dictionary.
The CLI must accept explicit archive paths, expected MD5 values, the SEC ticker
snapshot, event-cube symbols, and an external output root.

- [ ] **Step 4: Run focused verification**

Run: `python -m pytest tests/unit/data/test_uspto_patent_grants.py -q`

Run: `python -m ruff check src/us_intraday_lab/data/uspto_patent_grants.py scripts/build_uspto_patent_grant_training_snapshot.py tests/unit/data/test_uspto_patent_grants.py`

Expected: all focused tests pass and Ruff reports no errors.

- [ ] **Step 5: Commit the independently testable snapshot builder**

```powershell
git add -- src/us_intraday_lab/data/uspto_patent_grants.py scripts/build_uspto_patent_grant_training_snapshot.py tests/unit/data/test_uspto_patent_grants.py
git commit -m "Build USPTO patent-grant snapshot"
```

### Task 2: Causal five-session patent features

**Files:**
- Modify: `src/us_intraday_lab/data/uspto_patent_grants.py`
- Create: `scripts/build_uspto_patent_grant_training_features.py`
- Modify: `tests/unit/data/test_uspto_patent_grants.py`

**Interfaces:**
- Produces: `build_event_features(events: pd.DataFrame, grants: pd.DataFrame, identities: pd.DataFrame) -> pd.DataFrame`.
- Output adds exact issuer identity, batch size, five frozen family indicators, active patent IDs/count, latest public date, recency, prior-60-session audit fields, raw grant count, and explicit coverage reason.

- [ ] **Step 1: Write failing availability and causal-history tests**

```python
def test_grant_starts_next_session_and_expires_after_five():
    result = build_event_features(seven_sessions(), one_grant(), identity_frame())
    assert result.loc[0, "coverage_reason"] == "USPTO_NO_ACTIVE_GRANT"
    assert result.loc[1:5, "uspto_singleton_batch"].eq(1).all()
    assert result.loc[6, "coverage_reason"] == "USPTO_NO_ACTIVE_GRANT"

def test_acceleration_and_resumption_use_only_prior_sixty_sessions():
    result = build_event_features(sixty_two_sessions(), historical_batches(), identity_frame())
    target = result.loc[result["session_date"].eq(target_session)].iloc[0]
    assert target["uspto_accelerating_batch"] == 1
    assert target["uspto_prior_60_session_grant_count"] == expected_prior_count
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/unit/data/test_uspto_patent_grants.py -q`

Expected: failure because `build_event_features` does not exist.

- [ ] **Step 3: Implement causal projection and atomic cache publication**

Map each unique public grant-date batch to the first strictly later sample
session, activate it for five sessions, and aggregate overlapping batches.
Compute the prior-60-session count and median from availability positions only;
exclude the current batch from every `prior` statistic. Mark resumed innovation
only after 60 complete sample sessions with zero prior grants. Preserve raw
inventory before projection and never synthesize values for unmatched issuers.

- [ ] **Step 4: Run tests, lint, and commit**

Run: `python -m pytest tests/unit/data/test_uspto_patent_grants.py -q`

Run: `python -m ruff check src/us_intraday_lab/data/uspto_patent_grants.py scripts/build_uspto_patent_grant_training_features.py tests/unit/data/test_uspto_patent_grants.py`

```powershell
git add -- src/us_intraday_lab/data/uspto_patent_grants.py scripts/build_uspto_patent_grant_training_features.py tests/unit/data/test_uspto_patent_grants.py
git commit -m "Build causal USPTO patent features"
```

### Task 3: Frozen coverage and 400-cell diagnostic

**Files:**
- Create: `src/us_intraday_lab/uspto_patent_grant_feasibility.py`
- Create: `scripts/diagnose_uspto_patent_grant_training.py`
- Create: `tests/unit/test_uspto_patent_grant_feasibility.py`

**Interfaces:**
- Produces: `coverage_gate(features: pd.DataFrame, manifest: dict[str, object]) -> dict[str, object]`.
- Produces: `specifications() -> tuple[Specification, ...]`.
- Produces: `run_diagnostic(...) -> tuple[pd.DataFrame, dict[str, object]]`.

- [ ] **Step 1: Write failing coverage and grid tests**

```python
def test_gate_requires_hashes_100_issuers_5000_events_and_three_years():
    assert coverage_gate(inventory(100, 50), complete_manifest())["passed"] is True
    assert coverage_gate(inventory(99, 51), complete_manifest())["passed"] is False
    assert coverage_gate(inventory(100, 49), complete_manifest())["passed"] is False
    assert coverage_gate(inventory(100, 50), incomplete_manifest())["passed"] is False

def test_grid_has_exactly_400_unique_cells():
    assert len(specifications()) == len(set(specifications())) == 400
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/unit/test_uspto_patent_grant_feasibility.py -q`

Expected: collection failure because the feasibility module does not exist.

- [ ] **Step 3: Implement fail-closed diagnostic**

Define the five frozen continuation families and exact 400 specifications.
Validate event, archive-manifest, snapshot, and feature hashes. Apply coverage
before loading returns. Delegate standard/stress/delay evaluation to the
established evaluator with terminal decisions
`ACQUIRE_DEVELOPMENT_USPTO_PATENT_GRANT`,
`ABANDON_USPTO_PATENT_GRANT_COVERAGE_GATE`, and
`ABANDON_USPTO_PATENT_GRANT_NO_VERSION_CREATED`. Every summary keeps later data
false, versions zero, Paper false, and route forbidden.

- [ ] **Step 4: Run tests, lint, and commit**

Run: `python -m pytest tests/unit/test_uspto_patent_grant_feasibility.py -q`

Run: `python -m ruff check src/us_intraday_lab/uspto_patent_grant_feasibility.py scripts/diagnose_uspto_patent_grant_training.py tests/unit/test_uspto_patent_grant_feasibility.py`

```powershell
git add -- src/us_intraday_lab/uspto_patent_grant_feasibility.py scripts/diagnose_uspto_patent_grant_training.py tests/unit/test_uspto_patent_grant_feasibility.py
git commit -m "Implement USPTO patent feasibility diagnostic"
```

### Task 4: Acquire, execute, verify, and freeze

**Files:**
- Create: `research/results/2026-09-19-uspto-patent-grant-training-feasibility-summary.json`
- Create: `research/results/2026-09-19-uspto-patent-grant-training-feasibility-summary.md`
- Create: `memory/2026-09-19-uspto-patent-grant-training-local.md`

**Interfaces:**
- Produces immutable external raw archives, snapshot, feature cache, and cells plus tracked terminal evidence and structured fallback memory.

- [ ] **Step 1: Download the two declared files sequentially and hash immediately**

Use resumable downloads into
`E:\us-intraday-lab-data\us-market\data\staging\uspto_patent_grant_training_v1\raw`.
Write to `.part` files, verify the publisher MD5 before atomic rename, then
compute SHA-256. Do not request ODP credentials or substitute a mirror if the
Zenodo record is unavailable.

- [ ] **Step 2: Build the strict mapping snapshot and apply coverage**

Run the snapshot CLI against the frozen event symbols and SEC ticker snapshot.
If hash completeness, 100 uniquely mapped issuers, 5,000 symbol-patent events,
or three-year coverage fails, write the coverage-abandon summary, skip features
and cells, and freeze the evidence.

- [ ] **Step 3: Build features and run exactly 400 cells only after coverage passes**

Require exact artifact hashes, `status == "COMPLETE"`, and
`cells_completed == 400`. Do not load development or consumed periods.

- [ ] **Step 4: Verify terminal evidence**

Run: `python -m pytest tests/unit/data/test_uspto_patent_grants.py tests/unit/test_uspto_patent_grant_feasibility.py -q`

Run: `python -m ruff check src/us_intraday_lab/data/uspto_patent_grants.py src/us_intraday_lab/uspto_patent_grant_feasibility.py scripts/build_uspto_patent_grant_training_snapshot.py scripts/build_uspto_patent_grant_training_features.py scripts/diagnose_uspto_patent_grant_training.py tests/unit/data/test_uspto_patent_grants.py tests/unit/test_uspto_patent_grant_feasibility.py`

Run: `git diff --check`

Run: `python -m pytest -q`

Record known unrelated baseline failures without modifying them. Write fallback
memory with `summary`, `stage`, `kpi_version`, required tags, and `next_step`.

- [ ] **Step 5: Commit and push publishable evidence**

```powershell
git add -- src scripts tests research/results memory docs/superpowers
git commit -m "Freeze USPTO patent-grant feasibility"
git push origin codex/v550-v649-second-strategy
```

Keep raw archives, extracted tables, manifests, parquet caches, cells, logs, and
`state/` untracked.
