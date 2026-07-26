# Intraday Data Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the existing Tiingo IEX minute-bar archive into an immutable, quality-gated local snapshot that every later research and paper component reads through one canonical interface.

**Architecture:** A Python package owns versioned data contracts, calendar logic, archive inspection, canonicalization, partitioned Parquet output, and a read-only DuckDB research catalog. Import is copy-based and hash-addressed; no downstream component reads the old archive directly.

**Tech Stack:** Python 3.12, Pydantic 2, pandas, PyArrow, DuckDB, exchange-calendars, Typer, pytest, Ruff, mypy.

## Global Constraints

- Source archive: `G:\quant-agent-team-us\data\us_stock_data.tar.gz`.
- Expected source facts are evidence to verify, not constants to fake: approximately 1,418,418 1-minute rows, 63 symbols, and dates from `2025-06-23` through `2026-07-02`.
- Import only the minute-bar member(s) needed for this project; never extract the archive into Git-tracked paths.
- Canonical timestamps are timezone-aware UTC; session labels use `America/New_York`.
- Canonical bars contain `symbol`, `timestamp`, `open`, `high`, `low`, `close`, `volume`, `provider`, `feed`, `session_date`, and `ingested_at`.
- Raw and canonical data live under ignored `data/` paths. Git stores manifests and small synthetic fixtures only.
- A provider is authoritative per field. Do not combine Tiingo and Alpaca values into one bar.
- Derived 5-minute and 15-minute bars must be rebuilt only from canonical 1-minute bars, aligned to exchange sessions.
- A manifest hash, source hash, schema version, calendar version, code revision, and quality result identify every dataset snapshot.
- Missing bars, duplicates, invalid OHLC relationships, non-monotonic timestamps, and session-boundary violations are measured explicitly.
- Later plans may import only `us_intraday_lab.contracts` and `us_intraday_lab.data`; they may not reach into importer internals.

---

## File Structure

```text
pyproject.toml
src/us_intraday_lab/
  __init__.py
  cli.py
  settings.py
  contracts/
    __init__.py
    datasets.py
  data/
    __init__.py
    archive.py
    calendar.py
    canonicalize.py
    catalog.py
    quality.py
    resample.py
    snapshot.py
tests/
  fixtures/bars/
    minute_bars_valid.csv
    minute_bars_invalid.csv
  unit/contracts/test_datasets.py
  unit/data/test_calendar.py
  unit/data/test_canonicalize.py
  unit/data/test_quality.py
  unit/data/test_resample.py
  integration/data/test_archive_import.py
  integration/data/test_catalog.py
```

`contracts/datasets.py` is the stable cross-package schema. `data/archive.py` knows the legacy archive shape. `canonicalize.py` maps source rows into canonical rows. `quality.py` is pure validation. `snapshot.py` orchestrates import and immutable manifests. `catalog.py` exposes read-only SQL views.

## Task 1: Establish the Python Package and Quality Commands

**Files:**
- Create: `pyproject.toml`
- Create: `src/us_intraday_lab/__init__.py`
- Create: `src/us_intraday_lab/settings.py`
- Create: `src/us_intraday_lab/cli.py`
- Test: `tests/unit/test_settings.py`

- [ ] **Step 1: Write the failing path-settings test**

```python
from pathlib import Path

from us_intraday_lab.settings import LabPaths


def test_lab_paths_stay_under_configured_root(tmp_path: Path) -> None:
    paths = LabPaths.from_root(tmp_path)

    assert paths.raw == tmp_path / "data" / "raw"
    assert paths.canonical == tmp_path / "data" / "lake" / "canonical"
    assert paths.catalog == tmp_path / "data" / "catalog" / "research.duckdb"
    assert paths.manifests == tmp_path / "data" / "manifests"
```

- [ ] **Step 2: Run the test and confirm the package does not exist**

Run: `python -m pytest tests/unit/test_settings.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'us_intraday_lab'`.

- [ ] **Step 3: Add package metadata and deterministic paths**

Create `pyproject.toml` with:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "us-intraday-lab"
version = "0.1.0"
requires-python = ">=3.12,<3.13"
dependencies = [
  "duckdb>=1.3,<2",
  "exchange-calendars>=4.11,<5",
  "pandas>=2.2,<3",
  "pyarrow>=20,<22",
  "pydantic>=2.11,<3",
  "typer>=0.16,<1",
]

[project.optional-dependencies]
dev = [
  "mypy>=1.16,<2",
  "pandas-stubs>=2.2,<3",
  "pytest>=8.4,<9",
  "ruff>=0.12,<1",
]

[project.scripts]
intraday-lab = "us_intraday_lab.cli:app"

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.mypy]
python_version = "3.12"
strict = true
packages = ["us_intraday_lab"]
```

Create `settings.py`:

```python
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LabPaths:
    root: Path
    raw: Path
    canonical: Path
    catalog: Path
    manifests: Path

    @classmethod
    def from_root(cls, root: Path) -> "LabPaths":
        resolved = root.resolve()
        return cls(
            root=resolved,
            raw=resolved / "data" / "raw",
            canonical=resolved / "data" / "lake" / "canonical",
            catalog=resolved / "data" / "catalog" / "research.duckdb",
            manifests=resolved / "data" / "manifests",
        )
```

Create an empty package `__init__.py` and a Typer `app` in `cli.py`.

- [ ] **Step 4: Install editable dependencies and run all static checks**

Run:

```powershell
python -m pip install -e ".[dev]"
python -m pytest tests/unit/test_settings.py -q
ruff check .
ruff format --check .
python -m mypy src
```

Expected: all commands exit 0.

- [ ] **Step 5: Commit**

```powershell
git add pyproject.toml src tests/unit/test_settings.py
git commit -m "build: establish intraday lab Python package"
```

## Task 2: Define the Immutable Dataset Contract

**Files:**
- Create: `src/us_intraday_lab/contracts/__init__.py`
- Create: `src/us_intraday_lab/contracts/datasets.py`
- Test: `tests/unit/contracts/test_datasets.py`

- [ ] **Step 1: Write failing contract tests**

```python
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from us_intraday_lab.contracts.datasets import DatasetManifest, DatasetQuality


def test_manifest_requires_content_hashes_and_versions() -> None:
    manifest = DatasetManifest(
        dataset_id="tiingo-iex-minute-20260702",
        schema_version="1.0.0",
        source_uri="file:///G:/quant-agent-team-us/data/us_stock_data.tar.gz",
        source_sha256="a" * 64,
        content_sha256="b" * 64,
        code_revision="2d48ada",
        calendar_name="XNYS",
        calendar_version="2026a",
        created_at=datetime(2026, 7, 26, tzinfo=UTC),
        provider="tiingo",
        feed="iex",
        bar_size="1min",
        row_count=1,
        symbols=("SPY",),
        min_timestamp=datetime(2026, 7, 2, 13, 30, tzinfo=UTC),
        max_timestamp=datetime(2026, 7, 2, 13, 30, tzinfo=UTC),
        quality=DatasetQuality(passed=True),
    )

    assert manifest.dataset_id == "tiingo-iex-minute-20260702"


def test_manifest_rejects_non_sha256_hash() -> None:
    with pytest.raises(ValidationError):
        DatasetManifest.model_validate(
            {
                "dataset_id": "bad",
                "schema_version": "1.0.0",
                "source_uri": "file:///bad",
                "source_sha256": "short",
                "content_sha256": "b" * 64,
                "code_revision": "abc",
                "calendar_name": "XNYS",
                "calendar_version": "2026a",
                "created_at": "2026-07-26T00:00:00Z",
                "provider": "tiingo",
                "feed": "iex",
                "bar_size": "1min",
                "row_count": 0,
                "symbols": [],
                "min_timestamp": "2026-07-02T13:30:00Z",
                "max_timestamp": "2026-07-02T13:30:00Z",
                "quality": {"passed": False},
            }
        )
```

- [ ] **Step 2: Run and confirm missing contract failure**

Run: `python -m pytest tests/unit/contracts/test_datasets.py -q`

Expected: FAIL importing `DatasetManifest`.

- [ ] **Step 3: Implement strict Pydantic models**

Implement:

```python
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DatasetQuality(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    passed: bool
    duplicate_rows: int = Field(default=0, ge=0)
    missing_expected_bars: int = Field(default=0, ge=0)
    invalid_ohlc_rows: int = Field(default=0, ge=0)
    invalid_volume_rows: int = Field(default=0, ge=0)
    outside_session_rows: int = Field(default=0, ge=0)
    non_monotonic_groups: int = Field(default=0, ge=0)


class DatasetManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset_id: str = Field(min_length=1)
    schema_version: str
    source_uri: str
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    code_revision: str
    calendar_name: str
    calendar_version: str
    created_at: datetime
    provider: str
    feed: str
    bar_size: str
    row_count: int = Field(ge=0)
    symbols: tuple[str, ...]
    min_timestamp: datetime
    max_timestamp: datetime
    quality: DatasetQuality

    @model_validator(mode="after")
    def validate_range(self) -> "DatasetManifest":
        if self.min_timestamp > self.max_timestamp:
            raise ValueError("min_timestamp must not exceed max_timestamp")
        return self
```

- [ ] **Step 4: Add JSON round-trip and immutability assertions**

Extend the test to serialize with `model_dump_json()`, parse with `model_validate_json()`, and assert mutation raises a validation error.

- [ ] **Step 5: Run tests and commit**

```powershell
python -m pytest tests/unit/contracts/test_datasets.py -q
git add src/us_intraday_lab/contracts tests/unit/contracts
git commit -m "feat(data): define immutable dataset manifest"
```

## Task 3: Build Session-Aware Canonicalization and Quality Gates

**Files:**
- Create: `tests/fixtures/bars/minute_bars_valid.csv`
- Create: `tests/fixtures/bars/minute_bars_invalid.csv`
- Create: `src/us_intraday_lab/data/__init__.py`
- Create: `src/us_intraday_lab/data/calendar.py`
- Create: `src/us_intraday_lab/data/canonicalize.py`
- Create: `src/us_intraday_lab/data/quality.py`
- Test: `tests/unit/data/test_calendar.py`
- Test: `tests/unit/data/test_canonicalize.py`
- Test: `tests/unit/data/test_quality.py`

- [ ] **Step 1: Add a small synthetic fixture**

The valid CSV must contain exactly 20 invented rows across two symbols. The invalid CSV must include two symbols, a valid session open, one duplicate, one missing minute, one invalid high/low row, and one premarket row. Keep both files under 30 rows. Quality tests use the invalid file; successful archive-import tests use the valid file.

- [ ] **Step 2: Write failing calendar and canonicalization tests**

```python
from datetime import date

from us_intraday_lab.data.calendar import expected_minute_index


def test_xnys_regular_session_has_390_minutes() -> None:
    index = expected_minute_index(date(2026, 7, 2))

    assert len(index) == 390
    assert str(index.tz) == "UTC"
    assert index[0].isoformat() == "2026-07-02T13:30:00+00:00"
    assert index[-1].isoformat() == "2026-07-02T19:59:00+00:00"
```

```python
import pandas as pd

from us_intraday_lab.data.canonicalize import canonicalize_tiingo_rows


def test_canonicalizer_preserves_provider_and_utc_timestamp() -> None:
    source = pd.DataFrame(
        [
            {
                "ticker": "spy",
                "date": "2026-07-02T13:30:00Z",
                "open": 1.0,
                "high": 1.2,
                "low": 0.9,
                "close": 1.1,
                "volume": 100,
            }
        ]
    )

    bars = canonicalize_tiingo_rows(source, ingested_at="2026-07-26T00:00:00Z")

    assert bars.loc[0, "symbol"] == "SPY"
    assert bars.loc[0, "provider"] == "tiingo"
    assert bars.loc[0, "feed"] == "iex"
    assert str(bars["timestamp"].dt.tz) == "UTC"
```

- [ ] **Step 3: Run and confirm failures**

Run: `python -m pytest tests/unit/data/test_calendar.py tests/unit/data/test_canonicalize.py -q`

Expected: FAIL because the modules do not exist.

- [ ] **Step 4: Implement calendar and canonical mapping**

Use `exchange_calendars.get_calendar("XNYS")`; generate minutes from the official session open up to but excluding close. Reject naive timestamps and duplicate source columns. Sort canonical rows by `symbol, timestamp`.

- [ ] **Step 5: Write failing quality-gate tests**

```python
from us_intraday_lab.data.quality import assess_minute_bars


def test_quality_gate_fails_on_structural_errors(canonical_fixture) -> None:
    result = assess_minute_bars(canonical_fixture)

    assert result.passed is False
    assert result.duplicate_rows == 1
    assert result.invalid_ohlc_rows == 1
    assert result.outside_session_rows == 1
    assert result.missing_expected_bars >= 1
```

- [ ] **Step 6: Implement pure quality assessment**

The result passes only when duplicates, invalid OHLC, negative volume, outside-session bars, and non-monotonic groups are all zero. Missing-bar policy is explicit: missing bars are counted and make bootstrap import fail for `SPY`, `QQQ`, or `IWM`; robustness symbols are quarantined by symbol/session rather than forward-filled.

- [ ] **Step 7: Run all tests and commit**

```powershell
python -m pytest tests/unit/data -q
ruff check src tests
python -m mypy src
git add src/us_intraday_lab/data tests/fixtures tests/unit/data
git commit -m "feat(data): add canonical bars and quality gates"
```

## Task 4: Inspect and Import the Legacy Archive Reproducibly

**Files:**
- Create: `src/us_intraday_lab/data/archive.py`
- Create: `src/us_intraday_lab/data/snapshot.py`
- Extend: `src/us_intraday_lab/cli.py`
- Test: `tests/integration/data/test_archive_import.py`

- [ ] **Step 1: Write a failing import integration test with a temporary tarball**

Build a tiny `.tar.gz` in the test from `minute_bars_valid.csv`. Call `import_snapshot(...)`, then assert:

```python
assert manifest.source_sha256 == sha256_file(archive_path)
assert manifest.provider == "tiingo"
assert manifest.feed == "iex"
assert manifest.bar_size == "1min"
assert manifest.row_count == 20
assert output.exists()
assert output.name == "part-00000.parquet"
```

- [ ] **Step 2: Run and confirm failure**

Run: `python -m pytest tests/integration/data/test_archive_import.py -q`

Expected: FAIL because `import_snapshot` does not exist.

- [ ] **Step 3: Implement safe archive inspection**

`archive.py` must:

- enumerate members before extraction;
- reject absolute paths and `..` traversal;
- reject symbolic and hard links;
- stream only approved CSV/Parquet members;
- calculate the source SHA-256 without modifying the archive;
- return detected columns, member sizes, and row estimates for a dry run.

- [ ] **Step 4: Implement copy-based snapshot import**

`snapshot.py` must write to a temporary sibling directory, partition canonical Parquet by `bar_size=1min/session_date=YYYY-MM-DD/symbol=SYMBOL`, calculate content hashes in sorted path order, write `manifest.json`, and atomically rename the completed directory to `data/lake/canonical/<dataset_id>`. If any production symbol fails quality, delete only the verified temporary directory and leave prior snapshots untouched.

- [ ] **Step 5: Add CLI commands**

```text
intraday-lab data inspect-archive --archive <path>
intraday-lab data import-archive --archive <path> --root <repo>
intraday-lab data verify-snapshot --dataset-id <id> --root <repo>
```

`inspect-archive` is read-only and prints detected members and schema. `import-archive` prints the immutable dataset ID only after success. `verify-snapshot` recomputes hashes and quality.

- [ ] **Step 6: Run the synthetic integration test**

Run: `python -m pytest tests/integration/data/test_archive_import.py -q`

Expected: PASS.

- [ ] **Step 7: Inspect the real archive without importing**

Run:

```powershell
intraday-lab data inspect-archive --archive G:\quant-agent-team-us\data\us_stock_data.tar.gz
```

Expected: the command reports the actual member names, schema, size, date range, symbol count, and source hash. Compare them to the design evidence; if they differ, record the observed values in the generated manifest and stop for review if required columns are absent.

- [ ] **Step 8: Commit**

```powershell
git add src/us_intraday_lab/data/archive.py src/us_intraday_lab/data/snapshot.py src/us_intraday_lab/cli.py tests/integration/data
git commit -m "feat(data): import legacy archive as immutable snapshot"
```

## Task 5: Rebuild 5-Minute and 15-Minute Bars Without Lookahead

**Files:**
- Create: `src/us_intraday_lab/data/resample.py`
- Extend: `src/us_intraday_lab/data/snapshot.py`
- Test: `tests/unit/data/test_resample.py`

- [ ] **Step 1: Write failing alignment tests**

For a synthetic session beginning at 09:30 New York time, assert:

- the first 5-minute bar covers 09:30 through 09:34 and closes at 09:35;
- the first 15-minute bar covers 09:30 through 09:44 and closes at 09:45;
- OHLC uses first/max/min/last and volume sums;
- an incomplete interval is absent, not filled;
- different symbols never mix.

- [ ] **Step 2: Run and confirm failure**

Run: `python -m pytest tests/unit/data/test_resample.py -q`

- [ ] **Step 3: Implement exchange-session resampling**

Represent the derived bar timestamp as `available_at`, the instant after the interval completes. Include `source_bar_size="1min"` and the parent snapshot ID in derived metadata. Never use pandas day-boundary defaults; group by `symbol, session_date` and anchor intervals at the official session open.

- [ ] **Step 4: Add a causality regression**

Change the 09:45 1-minute close and assert it cannot change the 09:30–09:44 15-minute bar. This is the permanent lookahead guard.

- [ ] **Step 5: Run and commit**

```powershell
python -m pytest tests/unit/data/test_resample.py -q
git add src/us_intraday_lab/data/resample.py src/us_intraday_lab/data/snapshot.py tests/unit/data/test_resample.py
git commit -m "feat(data): derive causal intraday bar intervals"
```

## Task 6: Create the Read-Only DuckDB Research Catalog

**Files:**
- Create: `src/us_intraday_lab/data/catalog.py`
- Extend: `src/us_intraday_lab/cli.py`
- Test: `tests/integration/data/test_catalog.py`

- [ ] **Step 1: Write a failing catalog test**

Create a synthetic snapshot, build the catalog, and assert:

```sql
SELECT count(*) FROM bars_1m;
SELECT count(*) FROM bars_5m;
SELECT count(*) FROM bars_15m;
SELECT dataset_id, quality_passed FROM dataset_manifests;
```

Also assert the application connection is opened read-only and cannot `INSERT`.

- [ ] **Step 2: Implement catalog creation**

Create views over Parquet using explicit snapshot paths. Expose `bars_1m`, `bars_5m`, `bars_15m`, `dataset_manifests`, and `symbol_session_quality`. Store no mutable research state in DuckDB.

- [ ] **Step 3: Add catalog CLI and acceptance command**

```text
intraday-lab data build-catalog --dataset-id <id> --root <repo>
intraday-lab data accept --dataset-id <id> --root <repo>
```

`accept` verifies hashes, manifest/schema versions, production-symbol coverage, derived-bar lineage, and read-only catalog queries. It exits nonzero on any failure.

- [ ] **Step 4: Run the full Plan 1 gate**

```powershell
python -m pytest tests/unit tests/integration/data -q
ruff check .
ruff format --check .
python -m mypy src
intraday-lab data import-archive --archive G:\quant-agent-team-us\data\us_stock_data.tar.gz --root G:\us-intraday-lab
intraday-lab data build-catalog --dataset-id <printed-dataset-id> --root G:\us-intraday-lab
intraday-lab data accept --dataset-id <printed-dataset-id> --root G:\us-intraday-lab
```

Expected: tests and checks pass; the final command prints a quality summary and exits 0. Replace `<printed-dataset-id>` in the two later commands with the literal ID printed by the import command.

- [ ] **Step 5: Commit**

```powershell
git add src/us_intraday_lab/data/catalog.py src/us_intraday_lab/cli.py tests/integration/data/test_catalog.py
git commit -m "feat(data): expose accepted snapshots through DuckDB"
```

## Plan 1 Completion Criteria

- [ ] The real archive is inspected before import and its SHA-256 is recorded.
- [ ] No imported or derived data file is tracked by Git.
- [ ] `SPY`, `QQQ`, and `IWM` pass production-symbol coverage gates.
- [ ] Every 5-minute and 15-minute bar links to the immutable 1-minute snapshot.
- [ ] A second clean import of the same archive produces the same content hash and refuses to overwrite the existing snapshot.
- [ ] The catalog can query all bar sizes and manifests but cannot mutate them.
- [ ] All tests, Ruff, formatting, and mypy pass.
