# Polygon Listing Lifecycle Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and independently audit a causal monthly Polygon listing-lifecycle mapping for every symbol in the existing point-in-time eligible universe, stopping before strategy evaluation unless coverage is exactly 100%.

**Architecture:** A focused data module validates the immutable Polygon audit, selects the latest snapshot strictly before each month's first XNYS session, derives exact-ticker lifecycle history without identity stitching, and writes a hash-addressed Parquet catalog. A separate CLI emits immutable JSON/Markdown audit evidence and returns nonzero when the full-universe gate fails. Strategy formulas and returns remain a later plan whose prerequisite is this audit's `strategy_evaluation_permitted=true`.

**Tech Stack:** Python 3.12, pandas, PyArrow, exchange-calendars, pytest, Ruff, SHA-256 JSON manifests.

## Global Constraints

- Polygon snapshots remain independent reference data; do not rewrite Alpaca monthly eligibility.
- Use only snapshots strictly earlier than the first XNYS session of each decision month.
- Join by exact ticker after audited ASCII-uppercase normalization; never stitch by FIGI, CIK, name, or heuristic.
- Never use `delisted_utc`, `last_updated_utc`, future `active`, or future snapshots as features.
- Missing and ambiguous records are explicit exceptions; never map them to zero, neutral, cash, or an inferred lifecycle state.
- Required lifecycle coverage is 100% for every eligible month; any exception blocks all `v18010-v18109` return computation.
- Preserve source hashes and write outputs atomically and immutably.
- Do not add Paper, broker, submit, cancel, allocation, or observation-pool behavior.

---

## File map

- Create `src/us_intraday_lab/data/polygon_listing_lifecycle.py`: validation, cutoff selection, lifecycle derivation, coverage audit, and immutable catalog publication.
- Create `scripts/audit_polygon_listing_lifecycle.py`: command-line orchestration plus JSON/Markdown evidence.
- Create `tests/unit/data/test_polygon_listing_lifecycle.py`: synthetic causality, identity, missingness, provenance, and immutability tests.
- Create `tests/unit/test_polygon_listing_lifecycle_script.py`: CLI summary and fail-closed exit tests.
- Create `memory/2026-09-16-polygon-listing-lifecycle-coverage-local.md` only after the production audit, because MCP memory is unavailable and AGENTS.md requires a local fallback.

### Task 1: Causal lifecycle derivation

**Files:**
- Create: `src/us_intraday_lab/data/polygon_listing_lifecycle.py`
- Create: `tests/unit/data/test_polygon_listing_lifecycle.py`

**Interfaces:**
- Consumes: `load_historical_master_validation(path: Path) -> dict[str, object]` and Polygon `snapshots/asof=YYYY-MM-DD/{tickers.parquet,manifest.json}`.
- Produces: `derive_lifecycle_history(*, root: Path, validation_path: Path) -> tuple[pd.DataFrame, tuple[SnapshotLineage, ...]]`.
- Produces columns: `ticker`, `ticker_normalized`, `snapshot_asof`, `active`, `first_observed_active_month`, `active_tenure_months`, `left_censored`, `reactivated_this_month`, `lifecycle_bucket`, `snapshot_sha256`.

- [ ] **Step 1: Write failing tests for causal history, tenure, censoring, and reactivation**

```python
def test_derives_only_observed_monthly_lifecycle(tmp_path: Path) -> None:
    validation = write_validated_snapshots(
        tmp_path,
        {
            date(2018, 1, 31): [("OLD", True), ("RE", False)],
            date(2018, 2, 28): [("OLD", True), ("NEW", True), ("RE", True)],
            date(2018, 3, 31): [("OLD", True), ("NEW", True), ("RE", True)],
        },
    )
    frame, lineage = derive_lifecycle_history(root=tmp_path, validation_path=validation)
    march = frame.loc[frame["snapshot_asof"].eq(date(2018, 3, 31))].set_index("ticker")
    assert march.loc["OLD", "left_censored"]
    assert march.loc["OLD", "lifecycle_bucket"] == "left_censored"
    assert march.loc["NEW", "active_tenure_months"] == 1
    assert march.loc["NEW", "lifecycle_bucket"] == "new_0_3"
    assert not march.loc["RE", "reactivated_this_month"]
    february_re = frame.loc[
        frame["snapshot_asof"].eq(date(2018, 2, 28)) & frame["ticker"].eq("RE")
    ].iloc[0]
    assert february_re["reactivated_this_month"]
    assert len(lineage) == 3
```

- [ ] **Step 2: Run the focused test and confirm the import/function failure**

Run: `python -m pytest tests/unit/data/test_polygon_listing_lifecycle.py -v`

Expected: FAIL because `us_intraday_lab.data.polygon_listing_lifecycle` does not exist.

- [ ] **Step 3: Implement immutable snapshot validation and lifecycle derivation**

```python
@dataclass(frozen=True, slots=True)
class SnapshotLineage:
    asof: date
    parquet_path: str
    manifest_path: str
    content_sha256: str
    rows: int


def normalize_ticker(value: object) -> str:
    ticker = str(value).strip()
    if not ticker or not ticker.isascii():
        raise ValueError("LIFECYCLE_TICKER_NOT_ASCII")
    return ticker.upper()


def lifecycle_bucket(*, tenure: int, left_censored: bool) -> str:
    if left_censored:
        return "left_censored"
    if tenure <= 3:
        return "new_0_3"
    if tenure <= 12:
        return "young_4_12"
    if tenure <= 36:
        return "maturing_13_36"
    return "seasoned_37_plus"
```

Load every snapshot named by the validated 99-month master, verify its manifest namespace/provider/as-of/content hash/missing-data policy/no-splicing fields, reject duplicate `(normalized ticker, active)` rows and normalization collisions, and derive state using only the ordered prefix ending at the current snapshot. `reactivated_this_month` is true only for an immediately preceding observed false state followed by true; absence is not false. Do not load prohibited columns.

- [ ] **Step 4: Add and pass negative tests**

```python
@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("hash", "LIFECYCLE_SNAPSHOT_HASH_MISMATCH"),
        ("collision", "LIFECYCLE_NORMALIZATION_COLLISION"),
        ("duplicate", "LIFECYCLE_DUPLICATE_TICKER_ACTIVITY"),
    ],
)
def test_rejects_untrusted_snapshot_state(
    tmp_path: Path, mutation: str, message: str
) -> None:
    validation = write_validated_snapshots(
        tmp_path, {date(2018, 1, 31): [("A", True)]}
    )
    mutate_snapshot_fixture(tmp_path, mutation)
    with pytest.raises((RuntimeError, ValueError), match=message):
        derive_lifecycle_history(root=tmp_path, validation_path=validation)


def test_missing_previous_ticker_is_not_reactivation(tmp_path: Path) -> None:
    validation = write_validated_snapshots(
        tmp_path,
        {
            date(2018, 1, 31): [("A", True)],
            date(2018, 2, 28): [("A", True), ("B", True)],
        },
    )
    frame, _ = derive_lifecycle_history(root=tmp_path, validation_path=validation)
    row = frame.loc[frame["ticker"].eq("B")].iloc[0]
    assert not row["reactivated_this_month"]


def test_future_snapshot_cannot_change_prior_derived_rows(tmp_path: Path) -> None:
    validation = write_validated_snapshots(
        tmp_path, {date(2018, 1, 31): [("A", True)]}
    )
    before, _ = derive_lifecycle_history(root=tmp_path, validation_path=validation)
    append_validated_snapshot(tmp_path, validation, date(2018, 2, 28), [("A", False)])
    after, _ = derive_lifecycle_history(root=tmp_path, validation_path=validation)
    pd.testing.assert_frame_equal(
        before,
        after.loc[after["snapshot_asof"].eq(date(2018, 1, 31))].reset_index(drop=True),
    )
```

Run: `python -m pytest tests/unit/data/test_polygon_listing_lifecycle.py -v`

Expected: all tests PASS.

- [ ] **Step 5: Commit Task 1**

```powershell
git add -- src/us_intraday_lab/data/polygon_listing_lifecycle.py tests/unit/data/test_polygon_listing_lifecycle.py
git commit -m "Derive causal Polygon listing lifecycle"
```

### Task 2: Full-universe cutoff and coverage audit

**Files:**
- Modify: `src/us_intraday_lab/data/polygon_listing_lifecycle.py`
- Modify: `tests/unit/data/test_polygon_listing_lifecycle.py`

**Interfaces:**
- Consumes: lifecycle history from Task 1 and the unique `monthly_universe_sip_v2` decisions artifact.
- Produces: `build_lifecycle_coverage(*, root: Path, validation_path: Path) -> tuple[pd.DataFrame, dict[str, object]]`.
- Mapping columns: `month`, `symbol`, `snapshot_asof`, five lifecycle fields, `snapshot_sha256`, `universe_dataset_id`, `information_cutoff`.

- [ ] **Step 1: Write failing cutoff and coverage tests**

```python
def test_uses_latest_snapshot_strictly_before_first_xnys_session(tmp_path: Path) -> None:
    validation = write_three_month_coverage_fixture(tmp_path, missing_symbol=False)
    mapping, audit = build_lifecycle_coverage(root=tmp_path, validation_path=validation)
    january = mapping.loc[mapping["month"].eq(date(2019, 1, 1))]
    assert set(january["snapshot_asof"]) == {date(2018, 12, 31)}
    assert audit["coverage_ratio"] == 1.0
    assert audit["strategy_evaluation_permitted"] is True


def test_one_unmatched_symbol_blocks_entire_campaign(tmp_path: Path) -> None:
    validation = write_three_month_coverage_fixture(tmp_path, missing_symbol=True)
    _, audit = build_lifecycle_coverage(root=tmp_path, validation_path=validation)
    assert audit["strategy_evaluation_permitted"] is False
    assert audit["rejection_reasons"] == ["BLOCKED_LIFECYCLE_COVERAGE"]
    assert audit["exceptions"] == [{"month": "2019-01-01", "symbol": "MISSING", "reason": "UNMATCHED"}]
```

- [ ] **Step 2: Run tests and confirm `build_lifecycle_coverage` is absent**

Run: `python -m pytest tests/unit/data/test_polygon_listing_lifecycle.py -k coverage -v`

Expected: FAIL on missing interface.

- [ ] **Step 3: Implement strict monthly coverage**

```python
def first_xnys_session(month: date) -> date:
    end = (pd.Timestamp(month) + pd.offsets.MonthEnd(0)).date()
    sessions = _XNYS.sessions_in_range(pd.Timestamp(month), pd.Timestamp(end))
    if sessions.empty:
        raise RuntimeError("LIFECYCLE_XNYS_MONTH_EMPTY")
    return sessions[0].date()


def select_cutoff(asofs: Sequence[date], first_session: date) -> date:
    eligible = [value for value in asofs if value < first_session]
    if not eligible:
        raise RuntimeError("LIFECYCLE_PRIOR_SNAPSHOT_MISSING")
    return max(eligible)
```

Discover the single immutable decisions artifact with the same range/hash rules as `sip_five_minute_research._decisions_path`, retain only `eligible=true`, prove uppercase normalization is one-to-one per month in both sources, left-join without dropping rows, and classify exact exceptions as `UNMATCHED`, `AMBIGUOUS`, `NORMALIZATION_COLLISION`, `MISSING_LIFECYCLE_STATE`, or `CUTOFF_NOT_CAUSAL`. Sort exceptions deterministically. Permit evaluation only when every monthly numerator equals denominator and global ratio equals exactly `1.0`.

- [ ] **Step 4: Add completeness and anti-silent-drop assertions**

```python
assert audit["eligible_rows"] == audit["mapped_rows"] + audit["exception_rows"]
assert audit["months"] == len(audit["monthly_coverage"])
assert len(mapping) == audit["mapped_rows"]
assert all(row["coverage_ratio"] == 1.0 for row in audit["monthly_coverage"])
```

Run: `python -m pytest tests/unit/data/test_polygon_listing_lifecycle.py -v`

Expected: all tests PASS.

- [ ] **Step 5: Commit Task 2**

```powershell
git add -- src/us_intraday_lab/data/polygon_listing_lifecycle.py tests/unit/data/test_polygon_listing_lifecycle.py
git commit -m "Audit lifecycle coverage across eligible symbols"
```

### Task 3: Hash-addressed immutable publication and CLI

**Files:**
- Modify: `src/us_intraday_lab/data/polygon_listing_lifecycle.py`
- Create: `scripts/audit_polygon_listing_lifecycle.py`
- Create: `tests/unit/test_polygon_listing_lifecycle_script.py`
- Modify: `tests/unit/data/test_polygon_listing_lifecycle.py`

**Interfaces:**
- Produces: `publish_lifecycle_catalog(*, root: Path, validation_path: Path) -> dict[str, object]`.
- Publishes: `data/catalog/polygon_listing_lifecycle_v1/<dataset-id>/lifecycle.parquet`, `exceptions.parquet`, and `manifest.json`.
- CLI arguments: `--root`, `--historical-master-audit`, `--output-json`, `--output-md`.

- [ ] **Step 1: Write failing publication and CLI tests**

```python
def test_publish_is_hash_addressed_and_immutable(tmp_path: Path) -> None:
    first = publish_lifecycle_catalog(root=tmp_path, validation_path=validation)
    second = publish_lifecycle_catalog(root=tmp_path, validation_path=validation)
    assert first == second
    assert first["dataset_id"].startswith("polygon-listing-lifecycle-v1-")
    assert sha256(Path(first["mapping_path"])) == first["mapping_sha256"]


def test_cli_returns_nonzero_and_preserves_exceptions_when_blocked(
    tmp_path: Path,
) -> None:
    validation = write_three_month_coverage_fixture(tmp_path, missing_symbol=True)
    output_json = tmp_path / "audit.json"
    output_md = tmp_path / "audit.md"
    command = [
        sys.executable,
        "scripts/audit_polygon_listing_lifecycle.py",
        "--root",
        str(tmp_path),
        "--historical-master-audit",
        str(validation),
        "--output-json",
        str(output_json),
        "--output-md",
        str(output_md),
    ]
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    assert result.returncode == 2
    assert json.loads(output_json.read_text())["strategy_evaluation_permitted"] is False
    assert "Paper activation: false" in output_md.read_text()
```

- [ ] **Step 2: Run focused tests and confirm missing publication interfaces**

Run: `python -m pytest tests/unit/data/test_polygon_listing_lifecycle.py tests/unit/test_polygon_listing_lifecycle_script.py -v`

Expected: FAIL on missing `publish_lifecycle_catalog` and script.

- [ ] **Step 3: Implement atomic publication**

```python
identity = sha256(
    json.dumps(identity_payload, sort_keys=True, separators=(",", ":")).encode()
).hexdigest()[:24]
dataset_id = f"polygon-listing-lifecycle-v1-{identity}"
```

Write each Parquet file to a same-directory UUID temporary file, compute the final hash, atomically rename it, then write `manifest.json` last. If the dataset directory exists, validate every identity and hash and reuse it byte-for-byte; reject any collision. The manifest records the historical-master validation hash, all ordered snapshot hashes, universe dataset/hash, XNYS calendar version, mapping/exception hashes and counts, missing-data policy, `provider_splicing=FORBIDDEN`, `order_route=FORBIDDEN`, and `strategy_evaluation_permitted`.

- [ ] **Step 4: Implement immutable audit CLI**

```python
def main() -> None:
    args = parser.parse_args()
    manifest = publish_lifecycle_catalog(root=args.root, validation_path=args.historical_master_audit)
    write_immutable(args.output_json, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    write_immutable(args.output_md, render_markdown(manifest))
    print(json.dumps(secret_free_summary(manifest), sort_keys=True), flush=True)
    raise SystemExit(0 if manifest["strategy_evaluation_permitted"] else 2)
```

Markdown must include coverage numerator/denominator, every exception count, exact source/dataset hashes, `Provider splicing: FORBIDDEN`, `Strategy evaluation permitted: YES/NO`, and `Paper activation: false`.

- [ ] **Step 5: Run focused tests and static checks**

Run: `python -m pytest tests/unit/data/test_polygon_listing_lifecycle.py tests/unit/test_polygon_listing_lifecycle_script.py -v`

Expected: all tests PASS.

Run: `python -m ruff check src/us_intraday_lab/data/polygon_listing_lifecycle.py scripts/audit_polygon_listing_lifecycle.py tests/unit/data/test_polygon_listing_lifecycle.py tests/unit/test_polygon_listing_lifecycle_script.py`

Expected: `All checks passed!`

- [ ] **Step 6: Commit Task 3**

```powershell
git add -- src/us_intraday_lab/data/polygon_listing_lifecycle.py scripts/audit_polygon_listing_lifecycle.py tests/unit/data/test_polygon_listing_lifecycle.py tests/unit/test_polygon_listing_lifecycle_script.py
git commit -m "Publish immutable lifecycle coverage audit"
```

### Task 4: Production audit, regression verification, and checkpoint

**Files:**
- Create: `memory/2026-09-16-polygon-listing-lifecycle-coverage-local.md`
- Do not add generated data, audit outputs, caches, credentials, or `state/` to Git.

**Interfaces:**
- Consumes the real external root `E:\us-intraday-lab-data\us-market` and the exact validated Polygon historical-master audit used by the SIP audit.
- Produces a gate decision only: either `strategy_evaluation_permitted=true` or preserved blocking evidence.

- [ ] **Step 1: Locate and hash the exact production audits without reading credentials**

Run read-only discovery over the SIP audit and its `historical_master_validation_report_sha256`; require exactly one Polygon audit whose SHA-256 matches. Abort on zero or multiple matches.

- [ ] **Step 2: Run the production lifecycle audit**

```powershell
python scripts/audit_polygon_listing_lifecycle.py `
  --root E:\us-intraday-lab-data\us-market `
  --historical-master-audit <exact-matching-audit.json> `
  --output-json E:\us-intraday-lab-data\us-market\research\polygon-listing-lifecycle-v1-audit.json `
  --output-md E:\us-intraday-lab-data\us-market\research\polygon-listing-lifecycle-v1-audit.md
```

Expected when clear: exit 0, coverage ratio `1.0`, zero exceptions, and `strategy_evaluation_permitted=true`.

Expected when blocked: exit 2, exact exception rows preserved, no strategy returns or `v18010-v18109` evaluation artifacts created. A blocked result is a valid completion of this plan.

- [ ] **Step 3: Verify generated hashes and no forbidden side effects**

Reopen the manifest and both Parquet artifacts, recompute hashes and row equations, check that no source artifact mtime/hash changed, and run `git status --short` to prove only intended source/test/doc/memory files are candidates for commit.

- [ ] **Step 4: Run regression tests**

Run: `python -m pytest tests/unit/data tests/unit/test_polygon_listing_lifecycle_script.py -q`

Expected: PASS.

Run: `python -m pytest -q`

Expected: preserve the repository's pre-existing 16 unrelated research failures exactly; there must be zero new failures. Record both the pass count and the unchanged failure identities.

- [ ] **Step 5: Write the required local memory fallback**

The note must contain `summary`, `stage`, `kpi_version`, `tags`, and `next_step`, with tags `project:quant-agent-team`, `market:cn_a`, `freq:daily`, `stage:data-foundation`, and `status:passed|blocked`. It must state that this repository task concerns US intraday research despite the mandatory legacy CN-A memory tags.

- [ ] **Step 6: Commit the checkpoint and decide the next plan from evidence**

```powershell
git add -- memory/2026-09-16-polygon-listing-lifecycle-coverage-local.md
git commit -m "Record listing lifecycle coverage decision"
```

If the gate passes, write the separate `v18010-v18109` campaign implementation plan before strategy code. If it blocks, diagnose only the exact coverage exceptions; do not relax the 100% threshold, splice providers, drop symbols, or compute returns.
