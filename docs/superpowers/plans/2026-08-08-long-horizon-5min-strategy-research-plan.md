# Long-Horizon 5-Minute Strategy Research Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and run an isolated AAPL/QQQ five-minute research lane that promotes a long-only strategy to `paper_shadow` only when it passes all existing hard gates plus at least 90 OOS sessions, 10% annualized return after 1.5-times costs, and 0.5 IR versus QQQ.

**Architecture:** A new `long_horizon` package owns the five-minute data contract, conservative event engine, campaign-wide final-use ledger, OOS metrics, and orchestration. It reuses the existing closed strategy compiler, cost models, null/stability primitives, registry, and artifact conventions without changing the accepted one-minute snapshot or existing experiment evidence. A five-minute paper adapter aggregates only completed Alpaca one-minute bars and delegates intents to the existing paper risk boundary.

**Tech Stack:** Python 3.12, Pydantic 2, pandas, PyArrow, DuckDB, exchange-calendars, SQLite, pytest, Ruff, mypy.

## Global Constraints

- Long-only and paper-only; no real-money order path.
- Existing hard-gate thresholds and order remain unchanged for the one-minute lane.
- Five-minute production symbols are exactly ordered `("AAPL", "QQQ")`.
- Source is exactly `price_intraday_vol_5min.csv` from the verified legacy archive.
- Source timestamps are naive `America/New_York` regular-session timestamps and canonical timestamps are aware UTC.
- Historical fills occur at the next five-minute open; ambiguous same-bar stop/target resolution is adverse-first.
- Split is deterministic 60/20/20; combined validation/final OOS is at least 90 sessions and final alone is at least 60 sessions.
- The campaign final interval is consumable once across all proposal IDs for one dataset/split generation.
- New hard thresholds are cost-adjusted annualized return `>= 0.10` and IR versus QQQ `>= 0.5`.
- No strategy enters `paper_shadow` unless every old and new gate passes.

---

### Task 1: Five-Minute Source Contract and Safe Archive Read

**Files:**
- Create: `src/us_intraday_lab/long_horizon/__init__.py`
- Create: `src/us_intraday_lab/long_horizon/contracts.py`
- Create: `src/us_intraday_lab/long_horizon/data.py`
- Create: `tests/unit/long_horizon/test_data.py`
- Test: `tests/integration/long_horizon/test_archive_import.py`

**Interfaces:**
- Produces: `FiveMinuteSourceDeclaration`, `canonicalize_five_minute_rows(frame, declaration)`, and `read_declared_five_minute_member(archive, declaration)`.
- Consumes: `ArchiveReadLimits`, `inspect_archive`, `iter_archive_member_frames`, and `sha256_file` from `us_intraday_lab.data.archive`.

- [ ] **Step 1: Write failing source-contract tests**

```python
def declaration() -> FiveMinuteSourceDeclaration:
    return FiveMinuteSourceDeclaration(
        provider="tiingo",
        feed="iex",
        bar_size="5min",
        member_name="price_intraday_vol_5min.csv",
        member_sha256="ed35c8f515451ee243d1f2e42810742098dc841b5c7106867e2838eb228aabab",
        symbols=("AAPL", "QQQ"),
        source_timezone="America/New_York",
        expected_start_date=date(2025, 1, 2),
        expected_end_date=date(2026, 7, 2),
        ingested_at=datetime(2026, 8, 8, tzinfo=UTC),
    )


def test_declaration_is_closed_and_exact() -> None:
    item = declaration()
    assert item.symbols == ("AAPL", "QQQ")
    assert item.bar_size == "5min"
    with pytest.raises(ValidationError):
        FiveMinuteSourceDeclaration.model_validate(
            {**item.model_dump(), "symbols": ["QQQ", "AAPL"]}
        )


def test_canonicalizer_localizes_new_york_before_utc_conversion() -> None:
    result = canonicalize_five_minute_rows(
        pd.DataFrame(
            [{
                "symbol": "AAPL",
                "datetime": "2025-01-02 09:30:00",
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 10_000,
            }]
        ),
        declaration(),
    )
    assert result.loc[0, "timestamp"] == pd.Timestamp("2025-01-02T14:30:00Z")
```

- [ ] **Step 2: Run the tests and verify missing interfaces fail**

Run: `python -m pytest tests/unit/long_horizon/test_data.py -q`

Expected: collection fails because `us_intraday_lab.long_horizon.data` does not exist.

- [ ] **Step 3: Implement the closed contract and causal canonicalizer**

```python
class FiveMinuteSourceDeclaration(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    provider: Literal["tiingo"]
    feed: Literal["iex"]
    bar_size: Literal["5min"]
    member_name: Literal["price_intraday_vol_5min.csv"]
    member_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    symbols: tuple[Literal["AAPL", "QQQ"], Literal["AAPL", "QQQ"]]
    source_timezone: Literal["America/New_York"]
    expected_start_date: date
    expected_end_date: date
    ingested_at: datetime

    @model_validator(mode="after")
    def validate_scope(self) -> Self:
        if self.symbols != ("AAPL", "QQQ"):
            raise ValueError("symbols must be ordered AAPL, QQQ")
        if self.expected_start_date > self.expected_end_date:
            raise ValueError("expected date range must be chronological")
        if self.ingested_at.utcoffset() != timedelta(0):
            raise ValueError("ingested_at must be aware UTC")
        return self
```

`canonicalize_five_minute_rows` must parse `datetime` without `utc=True`, call
`.dt.tz_localize("America/New_York", ambiguous="raise", nonexistent="raise")`,
then `.dt.tz_convert("UTC")`, filter only declared symbols, and emit canonical
columns `symbol,timestamp,open,high,low,close,volume,provider,feed,session_date,ingested_at`.

- [ ] **Step 4: Add a real-archive integration test**

```python
def test_declared_member_identity_and_scope(real_archive: Path) -> None:
    frame = read_declared_five_minute_member(real_archive, declaration())
    assert tuple(sorted(frame["symbol"].unique())) == ("AAPL", "QQQ")
    assert frame["timestamp"].min() == pd.Timestamp("2025-01-02T14:30:00Z")
    assert frame["timestamp"].max() == pd.Timestamp("2026-07-02T19:55:00Z")
    assert len(frame) == 52_099
```

- [ ] **Step 5: Run Task 1 tests**

Run: `python -m pytest tests/unit/long_horizon/test_data.py tests/integration/long_horizon/test_archive_import.py -q`

Expected: all Task 1 tests pass.

- [ ] **Step 6: Commit Task 1**

```powershell
git add src/us_intraday_lab/long_horizon tests/unit/long_horizon/test_data.py tests/integration/long_horizon/test_archive_import.py
git commit -m "feat: add five-minute source contract"
```

---

### Task 2: Immutable Five-Minute Snapshot and Catalog

**Files:**
- Create: `src/us_intraday_lab/long_horizon/snapshot.py`
- Create: `src/us_intraday_lab/long_horizon/catalog.py`
- Create: `tests/integration/long_horizon/test_snapshot.py`
- Create: `tests/integration/long_horizon/test_catalog.py`
- Modify: `src/us_intraday_lab/cli.py`

**Interfaces:**
- Consumes: Task 1 source declaration and canonical frame.
- Produces: `import_five_minute_snapshot`, `verify_five_minute_snapshot`, `build_five_minute_catalog`, `accept_five_minute_dataset`, and CLI group `long-horizon-data`.

- [ ] **Step 1: Write failing deterministic snapshot tests**

```python
def test_snapshot_is_content_addressed_and_idempotent(tmp_path: Path, archive: Path) -> None:
    first = import_five_minute_snapshot(
        archive, declaration(), root=tmp_path, code_revision="abc123"
    )
    second = import_five_minute_snapshot(
        archive, declaration(), root=tmp_path, code_revision="abc123"
    )
    assert first == second
    assert first.dataset_id.startswith("tiingo-iex-5min-")
    assert first.bar_size == "5min"
    assert first.symbols == ("AAPL", "QQQ")


def test_quality_uses_shared_complete_sessions(tmp_path: Path, archive: Path) -> None:
    manifest = import_five_minute_snapshot(archive, declaration(), root=tmp_path)
    summary = accept_five_minute_dataset(manifest.dataset_id, root=tmp_path)
    assert summary.accepted_sessions >= 300
    assert summary.symbols == ("AAPL", "QQQ")
    assert summary.missing_expected_bars == 0
```

- [ ] **Step 2: Verify the tests fail before implementation**

Run: `python -m pytest tests/integration/long_horizon/test_snapshot.py tests/integration/long_horizon/test_catalog.py -q`

Expected: imports for snapshot and catalog interfaces fail.

- [ ] **Step 3: Implement immutable snapshot writing**

Write Parquet partitions to:

```text
data/lake/long_horizon/canonical/{dataset_id}/bar_size=5min/session_date=YYYY-MM-DD/symbol=SYMBOL/part-00000.parquet
```

Compute the dataset ID from canonical rows, declaration, calendar version,
source hash, and member hash. Write `manifest.json` and `import-evidence.json`
to a verified temporary sibling and atomically rename it. Existing destinations
must be verified and returned, never overwritten.

- [ ] **Step 4: Implement a read-only DuckDB catalog**

`build_five_minute_catalog` creates views:

```sql
CREATE VIEW bars_5m AS SELECT * FROM read_parquet($files, union_by_name=true);
CREATE VIEW dataset_manifests AS SELECT * FROM read_parquet($manifest_file);
CREATE VIEW symbol_session_quality AS SELECT * FROM read_parquet($quality_file);
```

`accept_five_minute_dataset` must reject any session not complete for both AAPL
and QQQ and expose only their shared accepted-session intersection.

- [ ] **Step 5: Add CLI commands**

```text
$datasetId = python -m us_intraday_lab.cli long-horizon-data import --archive G:\quant-agent-team-us\data\us_stock_data.tar.gz --root G:\us-intraday-lab
python -m us_intraday_lab.cli long-horizon-data verify --dataset-id $datasetId --root G:\us-intraday-lab
python -m us_intraday_lab.cli long-horizon-data build-catalog --dataset-id $datasetId --root G:\us-intraday-lab
python -m us_intraday_lab.cli long-horizon-data accept --dataset-id $datasetId --root G:\us-intraday-lab
```

- [ ] **Step 6: Run Task 2 tests and existing data tests**

Run: `python -m pytest tests/integration/long_horizon/test_snapshot.py tests/integration/long_horizon/test_catalog.py tests/unit/data tests/integration/data -q`

Expected: all selected tests pass and existing one-minute identities are unchanged.

- [ ] **Step 7: Commit Task 2**

```powershell
git add src/us_intraday_lab/long_horizon/snapshot.py src/us_intraday_lab/long_horizon/catalog.py src/us_intraday_lab/cli.py tests/integration/long_horizon
git commit -m "feat: build immutable five-minute dataset"
```

---

### Task 3: 60/20/20 Split and Campaign-Wide Final Ledger

**Files:**
- Create: `src/us_intraday_lab/long_horizon/splits.py`
- Create: `src/us_intraday_lab/long_horizon/final_ledger.py`
- Create: `tests/unit/long_horizon/test_splits.py`
- Create: `tests/integration/long_horizon/test_final_ledger.py`

**Interfaces:**
- Produces: `LongHorizonSplit`, `create_long_horizon_split`, `CampaignFinalLedger.reserve`, and `CampaignFinalLedger.consume`.
- Consumes: accepted shared sessions from Task 2.

- [ ] **Step 1: Write failing split tests**

```python
def test_long_horizon_split_is_deterministic_60_20_20() -> None:
    sessions = tuple(date(2025, 1, 1) + timedelta(days=i) for i in range(300))
    split = create_long_horizon_split(sessions, split_id="split-a")
    assert len(split.train_sessions) == 180
    assert len(split.validation_sessions) == 60
    assert len(split.final_test_sessions) == 60
    assert split.oos_sessions == split.validation_sessions + split.final_test_sessions


def test_split_fails_when_oos_or_final_is_too_short() -> None:
    sessions = tuple(date(2025, 1, 1) + timedelta(days=i) for i in range(200))
    with pytest.raises(ValueError, match="MINIMUM_LONG_HORIZON_OOS_NOT_MET"):
        create_long_horizon_split(sessions, split_id="too-short")
```

- [ ] **Step 2: Write failing campaign final reuse test**

```python
def test_campaign_final_cannot_be_consumed_by_second_proposal(tmp_path: Path) -> None:
    ledger = CampaignFinalLedger(tmp_path / "state" / "long_horizon_final.sqlite3")
    token = ledger.reserve(
        dataset_id="dataset-a", split_id="split-a", survivor_ids=("strategy-a",)
    )
    ledger.consume(token=token, proposal_id="proposal-a", evidence_sha256="a" * 64)
    with pytest.raises(FinalTestIsolationError, match="CAMPAIGN_FINAL_ALREADY_CONSUMED"):
        ledger.reserve(
            dataset_id="dataset-a", split_id="split-a", survivor_ids=("strategy-b",)
        )
```

- [ ] **Step 3: Run the tests to verify failure**

Run: `python -m pytest tests/unit/long_horizon/test_splits.py tests/integration/long_horizon/test_final_ledger.py -q`

Expected: missing long-horizon split and ledger interfaces.

- [ ] **Step 4: Implement exact split allocation**

Use deterministic largest-remainder weights `(6, 2, 2)`. `LongHorizonSplit`
must validate chronology, uniqueness, exact allocation, `len(oos_sessions) >= 90`,
and `len(final_test_sessions) >= 60`.

- [ ] **Step 5: Implement transactional final ledger**

SQLite schema:

```sql
CREATE TABLE campaign_final_use (
  dataset_id TEXT NOT NULL,
  split_id TEXT NOT NULL,
  reservation_token TEXT NOT NULL UNIQUE,
  survivor_ids_json TEXT NOT NULL,
  proposal_id TEXT,
  evidence_sha256 TEXT,
  consumed_at TEXT,
  PRIMARY KEY (dataset_id, split_id)
);
```

Use `BEGIN IMMEDIATE`; reservation and consumption are content-addressed and
idempotent only for the exact same identities. Proposal-ID changes cannot
create a second row for the same dataset/split.

- [ ] **Step 6: Run Task 3 tests**

Run: `python -m pytest tests/unit/long_horizon/test_splits.py tests/integration/long_horizon/test_final_ledger.py -q`

Expected: all Task 3 tests pass.

- [ ] **Step 7: Commit Task 3**

```powershell
git add src/us_intraday_lab/long_horizon/splits.py src/us_intraday_lab/long_horizon/final_ledger.py tests/unit/long_horizon/test_splits.py tests/integration/long_horizon/test_final_ledger.py
git commit -m "feat: seal long-horizon campaign final"
```

---

### Task 4: Closed Five-Minute DSL and Conservative Engine

**Files:**
- Modify: `src/us_intraday_lab/contracts/strategies.py`
- Modify: `src/us_intraday_lab/strategy/validator.py`
- Create: `src/us_intraday_lab/long_horizon/engine.py`
- Create: `tests/unit/long_horizon/test_strategy_contract.py`
- Create: `tests/integration/long_horizon/test_engine.py`

**Interfaces:**
- Produces: existing `StrategyDefinition` support for `signal_bar_size="5min"` and `FiveMinuteBacktestEngine.run`.
- Consumes: compiled strategy operators, existing cost scenarios, and Task 2 `bars_5m` frames.

- [ ] **Step 1: Write failing DSL tests**

```python
def test_five_minute_strategy_allows_only_aapl_qqq_long_scope() -> None:
    strategy = StrategyDefinition.model_validate(
        {
            **base_strategy_payload(),
            "symbols": ["AAPL", "QQQ"],
            "signal_bar_size": "5min",
        }
    )
    assert validate_strategy(strategy).passed


@pytest.mark.parametrize("symbols", [["QQQ", "AAPL"], ["AAPL"], ["AAPL", "QQQ", "SPY"]])
def test_five_minute_scope_rejects_other_symbol_sets(symbols: list[str]) -> None:
    strategy = StrategyDefinition.model_validate(
        {**base_strategy_payload(), "symbols": symbols, "signal_bar_size": "5min"}
    )
    assert not validate_strategy(strategy).passed
```

- [ ] **Step 2: Write failing engine timing tests**

```python
def test_entry_fills_at_next_five_minute_open() -> None:
    run = run_fixture_strategy(signal_at="2025-01-02T15:00:00Z")
    assert run.trades[0].entry_time == datetime(2025, 1, 2, 15, 5, tzinfo=UTC)
    assert run.trades[0].entry_price == 101.0


def test_same_bar_stop_and_target_uses_adverse_first() -> None:
    run = run_ambiguous_bar_fixture(long_entry=100.0, low=98.0, high=103.0)
    assert run.trades[0].exit_price == pytest.approx(99.0)
    assert run.trades[0].net_pnl < 0


def test_feature_bar_cannot_trade_before_available_at() -> None:
    run = run_fixture_strategy(signal_at="2025-01-02T15:00:00Z")
    assert all(intent.created_at >= datetime(2025, 1, 2, 15, 0, tzinfo=UTC) for intent in run.intents)
```

- [ ] **Step 3: Run Task 4 tests and verify failure**

Run: `python -m pytest tests/unit/long_horizon/test_strategy_contract.py tests/integration/long_horizon/test_engine.py -q`

Expected: `5min` is rejected and the engine interface is missing.

- [ ] **Step 4: Extend the closed contract without changing 15-minute behavior**

Change `SignalBarSize` to `Literal["5min", "15min"]`. Validator rules:

```python
if strategy.signal_bar_size == "5min":
    if strategy.symbols != ("AAPL", "QQQ"):
        issue("DSL_FIVE_MINUTE_SYMBOL_SCOPE", "symbols")
elif strategy.symbols != ("SPY", "QQQ", "IWM"):
    issue("DSL_PRODUCTION_SYMBOL_SCOPE", "symbols")
```

Keep all condition-depth, leaf-count, risk, sizing, order-type, and long-only
limits unchanged.

- [ ] **Step 5: Implement `FiveMinuteBacktestEngine`**

The engine receives completed bars with
`symbol,timestamp,available_at,open,high,low,close,volume,session_date`.
It evaluates features only at `available_at`, queues entries, and fills them at
the next row's open for the same symbol/session. Stops and targets inspect only
subsequent bars and choose stop first when both lie inside one bar. It emits the
same event, intent, trade, equity, and metric contracts as `BacktestEngine` so
existing artifact and null-test code can consume the result.

- [ ] **Step 6: Run engine, compiler, and old timing tests**

Run: `python -m pytest tests/unit/long_horizon/test_strategy_contract.py tests/integration/long_horizon/test_engine.py tests/unit/strategy tests/integration/backtest/test_engine_timing.py -q`

Expected: all tests pass; old 15-minute fingerprints and timing remain stable.

- [ ] **Step 7: Commit Task 4**

```powershell
git add src/us_intraday_lab/contracts/strategies.py src/us_intraday_lab/strategy/validator.py src/us_intraday_lab/long_horizon/engine.py tests/unit/long_horizon/test_strategy_contract.py tests/integration/long_horizon/test_engine.py
git commit -m "feat: add conservative five-minute engine"
```

---

### Task 5: OOS Annualized Return, QQQ IR, and Additive Gates

**Files:**
- Create: `src/us_intraday_lab/long_horizon/metrics.py`
- Create: `src/us_intraday_lab/long_horizon/gates.py`
- Modify: `src/us_intraday_lab/validation/stability.py`
- Modify: `src/us_intraday_lab/validation/null_tests.py`
- Modify: `src/us_intraday_lab/validation/gates.py`
- Create: `tests/unit/long_horizon/test_metrics.py`
- Create: `tests/unit/long_horizon/test_gates.py`
- Modify: `tests/unit/validation/test_stability.py`
- Modify: `tests/unit/validation/test_null_tests.py`

**Interfaces:**
- Produces: `LongHorizonOosMetrics`, `compute_long_horizon_oos_metrics`, `LongHorizonGateEvidence`, and `evaluate_long_horizon_gates`.
- Consumes: old `CandidateGateEvidence`/`evaluate_hard_gates`, chronological validation/final returns, QQQ closes, and 1.5-times cost drag.

- [ ] **Step 1: Write failing annualized-return and IR tests**

```python
def test_oos_metrics_use_geometric_return_and_sample_tracking_error() -> None:
    metrics = compute_long_horizon_oos_metrics(
        strategy_session_returns=(0.01, -0.005, 0.008),
        benchmark_session_returns=(0.004, -0.002, 0.003),
        cost_1_5x_session_returns=(0.009, -0.006, 0.007),
        annualization_sessions=252,
    )
    expected_total = math.prod((1.009, 0.994, 1.007)) - 1.0
    assert metrics.cost_1_5x_total_return == pytest.approx(expected_total)
    assert metrics.cost_1_5x_annualized_return == pytest.approx(
        (1.0 + expected_total) ** (252 / 3) - 1.0
    )
    active = (0.006, -0.003, 0.005)
    assert metrics.information_ratio == pytest.approx(
        statistics.fmean(active) / statistics.stdev(active) * math.sqrt(252)
    )


def test_ir_fails_closed_for_zero_tracking_error() -> None:
    with pytest.raises(ValueError, match="OOS_INFORMATION_RATIO_UNDEFINED"):
        compute_long_horizon_oos_metrics(
            strategy_session_returns=(0.01, 0.01),
            benchmark_session_returns=(0.0, 0.0),
            cost_1_5x_session_returns=(0.009, 0.009),
        )
```

- [ ] **Step 2: Write failing additive-gate test**

```python
def test_new_gates_do_not_replace_existing_gate_failures() -> None:
    result = evaluate_long_horizon_gates(
        LongHorizonGateEvidence(
            historical=old_evidence(base_net_return=-0.01),
            oos_sessions=120,
            cost_adjusted_annualized_return=0.15,
            information_ratio=0.8,
        )
    )
    assert "NONPOSITIVE_BASE_RETURN" in result.failure_reason_codes
    assert result.gate_results[-3].reason_code == "INSUFFICIENT_OOS_SESSIONS"
    assert result.gate_results[-2].reason_code == "COST_ADJUSTED_ANNUALIZED_RETURN_TOO_LOW"
    assert result.gate_results[-1].reason_code == "OOS_INFORMATION_RATIO_TOO_LOW"
```

- [ ] **Step 3: Run tests and verify missing interfaces fail**

Run: `python -m pytest tests/unit/long_horizon/test_metrics.py tests/unit/long_horizon/test_gates.py -q`

Expected: long-horizon metrics and gate modules are missing.

- [ ] **Step 4: Implement immutable OOS metrics**

`LongHorizonOosMetrics` fields are:

```python
oos_sessions: int
strategy_total_return: float
benchmark_total_return: float
excess_total_return: float
cost_1_5x_total_return: float
cost_1_5x_annualized_return: float
information_ratio: float
tracking_error: float
```

Require equal tuple lengths, at least two observations, finite values, returns
greater than `-1`, and positive sample tracking error.

- [ ] **Step 5: Implement additive hard gates**

Constants:

```python
MIN_OOS_SESSIONS = 90
MIN_COST_ADJUSTED_ANNUALIZED_RETURN = 0.10
MIN_OOS_INFORMATION_RATIO = 0.50
```

Call `evaluate_hard_gates` first, preserve all ten returned results in their
original order, append the three new results, and pass only when all thirteen
pass.

Parameterize existing symbol-sensitive validators without changing their
defaults:

```python
def assess_symbol_concentration(
    profit_by_symbol: Mapping[str, float],
    *,
    required_symbols: tuple[str, ...] = PRODUCTION_SYMBOLS,
    max_positive_profit_share: float = 0.70,
) -> SymbolConcentrationAssessment: ...


class NullTestConfig(_ClosedModel):
    symbols: tuple[str, ...] = PRODUCTION_SYMBOLS
    # retain all existing fields and defaults


class CandidateGateEvidence:
    # retain all existing fields
    required_symbols: tuple[str, ...] = PRODUCTION_SYMBOLS
```

Allow only the two exact scopes `("SPY", "QQQ", "IWM")` and
`("AAPL", "QQQ")`. Null opportunities may contain symbols from their declared
scope, and coverage must equal `NullTestConfig.symbols`. Old callers omit the
new arguments and retain byte-for-byte gate ordering and default scope.

- [ ] **Step 6: Run Task 5 and existing gate tests**

Run: `python -m pytest tests/unit/long_horizon/test_metrics.py tests/unit/long_horizon/test_gates.py tests/unit/validation/test_gates.py tests/unit/validation/test_stability.py tests/unit/validation/test_null_tests.py -q`

Expected: all tests pass and the old gate tuple remains unchanged.

- [ ] **Step 7: Commit Task 5**

```powershell
git add src/us_intraday_lab/long_horizon/metrics.py src/us_intraday_lab/long_horizon/gates.py tests/unit/long_horizon/test_metrics.py tests/unit/long_horizon/test_gates.py
git commit -m "feat: gate long-horizon return and information ratio"
```

---

### Task 6: Bounded Hypothesis Factory and One-Use Research Orchestrator

**Files:**
- Create: `src/us_intraday_lab/long_horizon/proposal.py`
- Create: `src/us_intraday_lab/long_horizon/variants.py`
- Create: `src/us_intraday_lab/long_horizon/orchestrator.py`
- Create: `tests/unit/long_horizon/test_variants.py`
- Create: `tests/integration/long_horizon/test_research.py`
- Modify: `src/us_intraday_lab/cli.py`

**Interfaces:**
- Produces: `LongHorizonHypothesisProposal`, `generate_long_horizon_variants`, `screen_long_horizon_campaign`, `finalize_long_horizon_campaign`, and CLI `long-horizon-research screen/finalize/resume/report`.
- Consumes: Tasks 2-5 plus existing stability, null-test, registry, and artifact primitives.

- [ ] **Step 1: Write failing proposal-scope tests**

```python
@pytest.mark.parametrize(
    "template",
    ["trend_pullback_5m", "opening_reclaim_5m", "vwap_reversion_5m", "momentum_5m"],
)
def test_only_approved_five_minute_templates_are_accepted(template: str) -> None:
    proposal = LongHorizonHypothesisProposal.model_validate(
        {**proposal_payload(), "entry_template": template}
    )
    assert proposal.symbols == ("AAPL", "QQQ")
    assert proposal.max_variants <= 50


def test_search_space_requires_three_distinct_neighbors() -> None:
    with pytest.raises(ValidationError, match="three robustness neighbors"):
        LongHorizonHypothesisProposal.model_validate(
            {**proposal_payload(), "parameter_ranges": {"return_1_max": {"values": [-0.001]}}}
        )
```

- [ ] **Step 2: Write failing final-ledger orchestration test**

```python
def test_second_experiment_cannot_reopen_consumed_campaign_final(tmp_path: Path) -> None:
    selection = screen_long_horizon_campaign(
        (proposal_a(), proposal_b()), dataset_id="data-a", root=tmp_path
    )
    first = finalize_long_horizon_campaign(selection, root=tmp_path)
    assert first.final_consumed
    with pytest.raises(FinalTestIsolationError, match="CAMPAIGN_FINAL_ALREADY_CONSUMED"):
        finalize_long_horizon_campaign(selection, root=tmp_path)
```

- [ ] **Step 3: Run Task 6 tests and verify failure**

Run: `python -m pytest tests/unit/long_horizon/test_variants.py tests/integration/long_horizon/test_research.py -q`

Expected: proposal, variants, and orchestrator interfaces are missing.

- [ ] **Step 4: Implement four closed templates**

Each template emits only JSON DSL. Baselines:

```python
TEMPLATES = {
    "trend_pullback_5m": ("ema_spread", "return_1", "range_position", "minutes_from_open"),
    "opening_reclaim_5m": ("return_3", "vwap_distance_bps", "volume_ratio", "minutes_from_open"),
    "vwap_reversion_5m": ("vwap_distance_bps", "rsi", "ema_spread", "minutes_from_open"),
    "momentum_5m": ("return_1", "return_3", "volume_ratio", "atr_bps"),
}
```

The proposal must contain exact AAPL/QQQ symbols, 3-50 variants, a finite
parameter grid, immutable seed, rationale, and AI/fixture provenance. Unknown
indicators, operators, templates, fields, or code strings fail validation.

- [ ] **Step 5: Implement staged orchestration**

Stages are append-only and hash chained:

```text
PROPOSAL_ACCEPTED
VARIANTS_GENERATED
TRAIN_COMPLETE
VALIDATION_COMPLETE
SELECTION_SEALED
CAMPAIGN_FINAL_RESERVED
FINAL_TEST_COMPLETE
LONG_HORIZON_GATES_COMPLETE
REGISTRY_COMPLETE
REPORT_COMPLETE
```

`screen_long_horizon_campaign` accepts all proposal files together, runs train
and validation preselection with every existing pre-final rule, then writes one
content-addressed selection manifest containing exactly one winning parameter
neighborhood. It cannot access or reserve final. `finalize_long_horizon_campaign`
validates that manifest, reserves the final ledger, runs final exactly once,
computes validation+final OOS metrics, appends three new gates, then consumes
the ledger with the final stage hash. A crash before consumption resumes only
the exact reservation and survivor identities.

- [ ] **Step 6: Add CLI commands and run integration tests**

```text
python -m us_intraday_lab.cli long-horizon-research screen --proposal-dir G:\us-intraday-lab\research\proposals\long_horizon --dataset-id $datasetId --root G:\us-intraday-lab
python -m us_intraday_lab.cli long-horizon-research finalize --selection-manifest $selectionManifest --root G:\us-intraday-lab
python -m us_intraday_lab.cli long-horizon-research resume --experiment-id $experimentId --root G:\us-intraday-lab
python -m us_intraday_lab.cli long-horizon-research report --experiment-id $experimentId --root G:\us-intraday-lab
```

Run: `python -m pytest tests/unit/long_horizon/test_variants.py tests/integration/long_horizon/test_research.py tests/integration/factory -q`

Expected: long-horizon and old factory integration tests pass.

- [ ] **Step 7: Commit Task 6**

```powershell
git add src/us_intraday_lab/long_horizon/proposal.py src/us_intraday_lab/long_horizon/variants.py src/us_intraday_lab/long_horizon/orchestrator.py src/us_intraday_lab/cli.py tests/unit/long_horizon/test_variants.py tests/integration/long_horizon/test_research.py
git commit -m "feat: orchestrate one-use long-horizon research"
```

---

### Task 7: Evidence Report and Registry Promotion

**Files:**
- Create: `src/us_intraday_lab/long_horizon/reporting.py`
- Create: `src/us_intraday_lab/reporting/templates/long_horizon_research_zh.md.j2`
- Create: `tests/integration/long_horizon/test_reporting.py`
- Modify: `src/us_intraday_lab/registry/store.py`

**Interfaces:**
- Produces: `write_long_horizon_research_report` and evidence-backed promotion to existing `paper_shadow` state.
- Consumes: Task 6 stage chain and existing registry transition API.

- [ ] **Step 1: Write failing report-content test**

```python
def test_report_exposes_oos_return_ir_and_all_gate_results(tmp_path: Path) -> None:
    path = write_long_horizon_research_report(completed_experiment(), root=tmp_path)
    text = path.read_text(encoding="utf-8")
    assert "成本后年化收益" in text
    assert "相对 QQQ 的信息比率" in text
    assert "OOS 交易日" in text
    assert "最终区间仅开启一次" in text
    assert "COST_ADJUSTED_ANNUALIZED_RETURN_TOO_LOW" in text
    assert "OOS_INFORMATION_RATIO_TOO_LOW" in text
```

- [ ] **Step 2: Write failing promotion test**

```python
def test_registry_promotion_requires_all_thirteen_gates(store: RegistryStore) -> None:
    decision = long_horizon_decision(all_passed=True)
    store.record_long_horizon_validation(decision)
    store.transition(
        strategy_id=decision.strategy_id,
        to_state="paper_shadow",
        validation_decision_id=decision.decision_id,
        reason_code="ALL_LONG_HORIZON_GATES_PASSED",
    )
    assert store.get_current_state(decision.strategy_id) == "paper_shadow"
```

- [ ] **Step 3: Run tests and verify failure**

Run: `python -m pytest tests/integration/long_horizon/test_reporting.py -q`

Expected: report interface and long-horizon validation persistence are missing.

- [ ] **Step 4: Implement evidence-only Chinese reporting**

Report exact, non-rounded source values alongside readable percentages for:
dataset/split/final-ledger identities, train/validation/final dates, OOS session
count, total and annualized returns, 1.5-times-cost annualized return, QQQ
return, excess return, tracking error, IR, Sharpe, MDD, PF, trades, exposure,
turnover, costs, symbol P&L, null thresholds, neighbors, all gate outcomes,
ranking, lifecycle state, code revision, engine version, and artifact hashes.

- [ ] **Step 5: Make registry validation additive and immutable**

Persist the complete thirteen-gate decision canonical JSON and hash. Existing
one-minute decisions remain valid. Long-horizon promotion requires reason
`ALL_LONG_HORIZON_GATES_PASSED`; any missing or failed gate rejects promotion.

- [ ] **Step 6: Run report, registry, and lifecycle tests**

Run: `python -m pytest tests/integration/long_horizon/test_reporting.py tests/unit/registry tests/integration/reporting -q`

Expected: all tests pass.

- [ ] **Step 7: Commit Task 7**

```powershell
git add src/us_intraday_lab/long_horizon/reporting.py src/us_intraday_lab/reporting/templates/long_horizon_research_zh.md.j2 src/us_intraday_lab/registry/store.py tests/integration/long_horizon/test_reporting.py
git commit -m "feat: report long-horizon promotion evidence"
```

---

### Task 8: Five-Minute Paper Signal Adapter

**Files:**
- Create: `src/us_intraday_lab/paper/five_minute.py`
- Create: `tests/unit/paper/test_five_minute.py`
- Modify: `src/us_intraday_lab/paper/market_data.py`
- Modify: `src/us_intraday_lab/paper/session.py`
- Modify: `src/us_intraday_lab/paper/risk.py`

**Interfaces:**
- Produces: `FiveMinuteBarAggregator.on_minute_bar` and paper support for audited AAPL/QQQ five-minute strategies.
- Consumes: Alpaca IEX one-minute `MarketBarClosed`, compiled strategy, existing risk and broker boundaries.

- [ ] **Step 1: Write failing aggregation and timing tests**

```python
def test_emits_only_after_five_distinct_closed_minutes() -> None:
    aggregator = FiveMinuteBarAggregator(symbols=("AAPL", "QQQ"))
    emitted = [aggregator.on_minute_bar(bar(minute=i)) for i in range(5)]
    assert emitted[:4] == [None, None, None, None]
    assert emitted[4].available_at == datetime(2026, 8, 10, 13, 35, tzinfo=UTC)


def test_gap_suppresses_incomplete_five_minute_bar() -> None:
    aggregator = FiveMinuteBarAggregator(symbols=("AAPL", "QQQ"))
    for minute in (0, 1, 3, 4):
        assert aggregator.on_minute_bar(bar(minute=minute)) is None
    assert "INCOMPLETE_FIVE_MINUTE_BAR" in aggregator.health_reason_codes


def test_no_order_before_completed_signal_bar() -> None:
    session = paper_session_with_five_minute_strategy()
    session.on_market_bar(bar(minute=4))
    assert session.broker.submitted_orders == ()
```

- [ ] **Step 2: Run tests and verify missing adapter fails**

Run: `python -m pytest tests/unit/paper/test_five_minute.py -q`

Expected: `FiveMinuteBarAggregator` is missing.

- [ ] **Step 3: Implement strict aggregation**

Bucket by XNYS session, symbol, and five-minute boundary. Require five unique
consecutive regular-session minutes. OHLCV aggregation is first open, maximum
high, minimum low, last close, summed volume. Emit once with a deterministic
provider event ID and `available_at` equal to the boundary close.

- [ ] **Step 4: Extend paper scope without weakening risk**

Only registry strategies whose definition has `signal_bar_size="5min"` and
symbols exactly AAPL/QQQ use the adapter. Existing 15-minute trio behavior is
unchanged. Risk still rejects shorts, leverage, missing state, stale data,
incomplete streams, storage faults, and non-paper broker configuration.

- [ ] **Step 5: Run paper tests**

Run: `python -m pytest tests/unit/paper/test_five_minute.py tests/unit/paper tests/integration/paper -q`

Expected: all paper tests pass without network access or order submission.

- [ ] **Step 6: Commit Task 8**

```powershell
git add src/us_intraday_lab/paper/five_minute.py src/us_intraday_lab/paper/market_data.py src/us_intraday_lab/paper/session.py src/us_intraday_lab/paper/risk.py tests/unit/paper/test_five_minute.py
git commit -m "feat: aggregate five-minute paper signals"
```

---

### Task 9: Import Real Data and Run the Sealed Research Campaign

**Files:**
- Create: `research/proposals/long_horizon/2026-08-08-trend-pullback-v1.json`
- Create: `research/proposals/long_horizon/2026-08-08-opening-reclaim-v1.json`
- Create: `research/proposals/long_horizon/2026-08-08-vwap-reversion-v1.json`
- Create: `research/proposals/long_horizon/2026-08-08-momentum-v1.json`
- Generate: ignored immutable dataset, experiment, backtest, report, registry, and final-ledger artifacts

**Interfaces:**
- Consumes: complete Tasks 1-8.
- Produces: one formal campaign result and zero or more `paper_shadow` strategies.

- [ ] **Step 1: Import and verify the real five-minute snapshot**

Run:

```powershell
$datasetId = python -m us_intraday_lab.cli long-horizon-data import --archive G:\quant-agent-team-us\data\us_stock_data.tar.gz --root G:\us-intraday-lab
python -m us_intraday_lab.cli long-horizon-data verify --dataset-id $datasetId --root G:\us-intraday-lab
python -m us_intraday_lab.cli long-horizon-data build-catalog --dataset-id $datasetId --root G:\us-intraday-lab
python -m us_intraday_lab.cli long-horizon-data accept --dataset-id $datasetId --root G:\us-intraday-lab
```

Expected: exact AAPL/QQQ scope, at least 300 accepted shared sessions, at least
90 combined OOS sessions, and at least 60 final sessions.

- [ ] **Step 2: Explore only train and validation**

Create the four named proposal files listed above, then run:

```powershell
$selectionManifest = python -m us_intraday_lab.cli long-horizon-research screen --proposal-dir G:\us-intraday-lab\research\proposals\long_horizon --dataset-id $datasetId --root G:\us-intraday-lab
```

The `screen` command runs train and validation stages only. Preserve rejected
variants and do not reserve or read final until one neighborhood passes all
pre-final rules, including
positive 1.5-times-cost return, at least 100 historical trades, PF >= 1.15,
MDD <= 8%, at least 60% profitable rolling windows, stable neighbors, stable
start dates, concentration <= 70%, and both null tests.

- [ ] **Step 3: Freeze the single survivor neighborhood**

Commit the exact proposal, catalog/generator versions, and any code required to
represent it before reserving the campaign final.

```powershell
git add research/proposals src tests docs
git commit -m "research: freeze long-horizon survivor neighborhood"
git push origin codex/bootstrap-first-paper-session
```

- [ ] **Step 4: Consume campaign final once**

Run:

```powershell
$experimentId = python -m us_intraday_lab.cli long-horizon-research finalize --selection-manifest $selectionManifest --root G:\us-intraday-lab
```

Expected: the ledger records one final consumption for the dataset/split. Do
not create another proposal against the consumed interval.

- [ ] **Step 5: Audit every completion requirement**

Inspect the generated stage chain and report. At least one strategy must prove:

```text
long_only = true
paper_only = true
oos_sessions >= 90
cost_1_5x_annualized_return >= 0.10
information_ratio_vs_qqq >= 0.50
max_drawdown <= 0.08
closed_trades >= 100
profit_factor >= 1.15
all_existing_hard_gates = passed
all_new_hard_gates = passed
registry_state = paper_shadow
campaign_final_consumptions = 1
```

If no strategy passes, record the experiment as failed and wait for newly
accrued forward data; never reopen the final or lower thresholds.

- [ ] **Step 6: Commit research artifacts allowed by repository policy**

Commit proposals, source changes, tests, and generated text reports. Do not add
SQLite databases, raw archives, Parquet snapshots, credentials, or broker data.

---

### Task 10: Full Verification and Publication

**Files:**
- Modify only files required by failures directly caused by Tasks 1-9

**Interfaces:**
- Consumes: complete implementation and formal campaign evidence.
- Produces: verified branch state published to the existing remote.

- [ ] **Step 1: Run formatting and static checks**

Run:

```powershell
python -m ruff check .
python -m mypy src
git diff --check
```

Expected: all commands exit 0.

- [ ] **Step 2: Run the full test suite**

Run: `python -m pytest -q`

Expected: every test passes; warnings are reviewed and no warning invalidates
timing, data, gate, final-isolation, or paper evidence.

- [ ] **Step 3: Verify repository scope**

Run:

```powershell
git status --short
git diff --cached --stat
git ls-files | Select-String -Pattern "\.sqlite3$|\.duckdb$|\.parquet$|us_stock_data\.tar\.gz$"
```

Expected: only intended code, tests, proposals, specifications, plans, and text
reports are tracked; no secret or raw-data artifact is staged.

- [ ] **Step 4: Commit and push**

```powershell
git add src tests research/proposals docs/superpowers/specs docs/superpowers/plans reports/generated/research
git commit -m "feat: qualify long-horizon five-minute strategies"
git push origin codex/bootstrap-first-paper-session
```

- [ ] **Step 5: Completion audit**

Re-read the design, plan, formal stage chain, generated report, registry state,
test output, branch, and remote tracking state. Mark the goal complete only if
every requirement in Task 9 Step 5 has authoritative current evidence.
