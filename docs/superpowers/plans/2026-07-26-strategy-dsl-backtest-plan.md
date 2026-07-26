# Strategy DSL and Backtest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compile safe, versioned, long-only strategy definitions into a deterministic event-driven backtest that respects completed-bar timing, integer shares, account limits, and explicit transaction costs.

**Architecture:** Pydantic models represent a non-executable strategy DSL. A validator rejects unsafe or unbounded definitions before a compiler maps approved operators to internal feature and rule objects. An event-driven engine consumes immutable minute bars, exposes completed 15-minute features, submits intents no earlier than the next 1-minute bar, and records an append-only audit trail.

**Tech Stack:** Python 3.12, Pydantic 2, pandas, NumPy, PyArrow, DuckDB, pytest, Ruff, mypy.

## Global Constraints

- Complete the data foundation plan first and use only an accepted `DatasetManifest`.
- AI output is data, never Python, SQL, shell, Jinja, lambda expressions, import paths, or serialized callables.
- Release-one DSL supports a finite allowlist of price/volume indicators, comparisons, boolean groups, time windows, stops, profit targets, maximum holding time, cooldowns, and sizing presets.
- Strategies are long-only and can emit only `ENTER_LONG`, `EXIT_LONG`, or `HOLD`.
- Production paper symbols are exactly `SPY`, `QQQ`, and `IWM`.
- A strategy may enter at most 3 times per session; the account may hold at most 3 positions.
- Positions use integer shares, no margin, no leverage, and no overnight holding.
- Signals use a completed 15-minute bar. An order cannot fill before the next 1-minute bar.
- Release one supports market and limit orders only.
- Every run uses optimistic, base, and stress fill/cost models. Zero-cost is diagnostic only.
- Determinism requires fixed strategy, dataset, engine, calendar, and cost-model versions.
- A backtest failure returns a typed failure result and audit events; it must not return partial performance as success.

---

## File Structure

```text
src/us_intraday_lab/
  contracts/
    strategies.py
    backtests.py
    orders.py
  strategy/
    operators.py
    validator.py
    compiler.py
    features.py
    runtime.py
  backtest/
    clock.py
    costs.py
    fills.py
    portfolio.py
    engine.py
    metrics.py
tests/
  fixtures/strategies/
    valid_momentum_pullback.json
    invalid_freeform_code.json
  unit/strategy/
    test_contract.py
    test_validator.py
    test_features.py
    test_compiler.py
  unit/backtest/
    test_clock.py
    test_costs.py
    test_fills.py
    test_portfolio.py
    test_metrics.py
  integration/backtest/
    test_engine_timing.py
    test_determinism.py
```

`contracts/strategies.py` owns wire-format definitions. `strategy/validator.py` owns static safety. `compiler.py` converts only allowlisted nodes. `runtime.py` is stateful per strategy/symbol/session. The backtest package owns market time, fills, cash, positions, and results; it never parses arbitrary expressions.

## Task 1: Define the Closed Strategy and Backtest Contracts

**Files:**
- Modify: `pyproject.toml`
- Create: `src/us_intraday_lab/contracts/strategies.py`
- Create: `src/us_intraday_lab/contracts/orders.py`
- Create: `src/us_intraday_lab/contracts/backtests.py`
- Test: `tests/unit/strategy/test_contract.py`

- [ ] **Step 1: Write failing contract tests**

```python
import pytest
from pydantic import ValidationError

from us_intraday_lab.contracts.strategies import StrategyDefinition


VALID = {
    "strategy_id": "mom-pullback-v1",
    "dsl_version": "1.0.0",
    "symbols": ["SPY", "QQQ", "IWM"],
    "signal_bar_size": "15min",
    "entry": {
        "all": [
            {"indicator": "ema_spread", "op": "gt", "value": 0.0},
            {"indicator": "rsi", "op": "lt", "value": 45.0},
        ]
    },
    "exit": {"any": [{"indicator": "rsi", "op": "gt", "value": 65.0}]},
    "risk": {
        "stop_loss_bps": 35,
        "take_profit_bps": 70,
        "max_holding_minutes": 90,
        "cooldown_minutes": 30,
        "max_entries_per_session": 3,
        "sizing_preset": "equal_risk_conservative",
    },
    "order_type": "market",
}


def test_strategy_contract_accepts_only_closed_dsl() -> None:
    strategy = StrategyDefinition.model_validate(VALID)
    assert strategy.signal_bar_size == "15min"


def test_strategy_contract_rejects_extra_code_field() -> None:
    payload = {**VALID, "python": "import os; os.system('whoami')"}
    with pytest.raises(ValidationError):
        StrategyDefinition.model_validate(payload)
```

- [ ] **Step 2: Run and confirm contract import failure**

Run: `python -m pytest tests/unit/strategy/test_contract.py -q`

- [ ] **Step 3: Implement discriminated, frozen Pydantic models**

Add `numpy>=2.2,<3` as a direct runtime dependency in `pyproject.toml`, then reinstall the editable package with `python -m pip install -e ".[dev]"`. Use `Literal` and `extra="forbid"` throughout. Exact release-one allowlists:

```python
IndicatorName = Literal[
    "return_1",
    "return_3",
    "ema_spread",
    "rsi",
    "atr_bps",
    "volume_ratio",
    "vwap_distance_bps",
    "range_position",
    "minutes_from_open",
]
ComparisonOp = Literal["gt", "gte", "lt", "lte"]
SignalBarSize = Literal["15min"]
OrderType = Literal["market", "limit"]
SizingPreset = Literal[
    "equal_cash_conservative",
    "equal_risk_conservative",
]
```

Create recursive `AllCondition`, `AnyCondition`, and leaf `ComparisonCondition` with a maximum nesting depth enforced later by the validator. Do not include a generic expression string.

- [ ] **Step 4: Add versioned order and result contracts**

Define frozen models for:

- `OrderIntent`: run, strategy, symbol, session, side, type, quantity, limit price, signal time, eligible time, reason code, idempotency key.
- `OrderEvent`: status transition, broker/backtest ID, event time, requested and filled quantities/prices, fees, rejection reason.
- `BacktestJob`: immutable IDs for strategy, dataset, engine, calendar, and three cost models.
- `BacktestResult`: status, typed failure, metrics by cost scenario, trades URI, events URI, and content hash.

- [ ] **Step 5: Test JSON round trips and commit**

```powershell
python -m pytest tests/unit/strategy/test_contract.py -q
git add src/us_intraday_lab/contracts tests/unit/strategy/test_contract.py
git commit -m "feat(strategy): define closed DSL and backtest contracts"
```

## Task 2: Enforce Static DSL Safety and Compile Allowlisted Rules

**Files:**
- Create: `src/us_intraday_lab/strategy/__init__.py`
- Create: `src/us_intraday_lab/strategy/operators.py`
- Create: `src/us_intraday_lab/strategy/validator.py`
- Create: `src/us_intraday_lab/strategy/compiler.py`
- Create: `tests/fixtures/strategies/valid_momentum_pullback.json`
- Create: `tests/fixtures/strategies/invalid_freeform_code.json`
- Test: `tests/unit/strategy/test_validator.py`
- Test: `tests/unit/strategy/test_compiler.py`

- [ ] **Step 1: Write the failing safety matrix**

Parameterize cases that must be rejected:

- symbol outside `SPY`, `QQQ`, `IWM`;
- `max_entries_per_session > 3`;
- non-15-minute signal bars;
- negative or zero stop/target/holding/cooldown;
- limit offset outside the configured safe range;
- unknown indicator or comparison;
- condition nesting deeper than 3;
- more than 12 leaf conditions;
- contradictory leaf comparisons on the same indicator;
- `python`, `sql`, template, URL, file path, import, or callable fields;
- exit rules that can increase exposure.

Each rejection must contain a stable machine code such as `DSL_UNSUPPORTED_SYMBOL`.

- [ ] **Step 2: Implement validation separate from Pydantic parsing**

Return:

```python
@dataclass(frozen=True)
class ValidationIssue:
    code: str
    path: str
    message: str


@dataclass(frozen=True)
class StrategyValidation:
    passed: bool
    issues: tuple[ValidationIssue, ...]
```

The validator must collect all static issues in deterministic path order. Pydantic catches malformed structure; the safety validator catches domain limits.

- [ ] **Step 3: Write compiler tests**

Assert the valid JSON compiles to typed operator nodes. Assert a handcrafted object cannot cause the compiler to resolve modules, evaluate strings, access attributes, or execute code. The compiler dispatch table must be a literal map from allowlisted indicator names to internal functions.

- [ ] **Step 4: Implement the compiler**

Use explicit visitors:

```python
INDICATORS: dict[str, IndicatorFn] = {
    "return_1": feature_return_1,
    "return_3": feature_return_3,
    "ema_spread": feature_ema_spread,
    "rsi": feature_rsi,
    "atr_bps": feature_atr_bps,
    "volume_ratio": feature_volume_ratio,
    "vwap_distance_bps": feature_vwap_distance_bps,
    "range_position": feature_range_position,
    "minutes_from_open": feature_minutes_from_open,
}
```

No `eval`, `exec`, `getattr` on user input, imports derived from payloads, or dynamically generated SQL.

- [ ] **Step 5: Run security grep and tests**

```powershell
python -m pytest tests/unit/strategy/test_validator.py tests/unit/strategy/test_compiler.py -q
rg -n "\beval\(|\bexec\(|pickle|cloudpickle|marshal" src
```

Expected: tests pass and the grep returns no matches.

- [ ] **Step 6: Commit**

```powershell
git add src/us_intraday_lab/strategy tests/fixtures/strategies tests/unit/strategy
git commit -m "feat(strategy): validate and compile constrained DSL"
```

## Task 3: Compute Causal Features at Completed-Bar Boundaries

**Files:**
- Create: `src/us_intraday_lab/strategy/features.py`
- Create: `src/us_intraday_lab/strategy/runtime.py`
- Test: `tests/unit/strategy/test_features.py`
- Test: `tests/integration/backtest/test_engine_timing.py`

- [ ] **Step 1: Write feature-timing tests**

Create two 15-minute bars. At `09:45:00 America/New_York`, the runtime may expose only the bar covering 09:30–09:44. Mutating any 1-minute input at or after 09:45 must not change that feature vector.

- [ ] **Step 2: Implement a feature frame with explicit availability**

Every feature row contains:

```text
symbol
session_date
bar_start
available_at
feature_set_version
return_1
return_3
ema_spread
rsi
atr_bps
volume_ratio
vwap_distance_bps
range_position
minutes_from_open
```

Rolling features use only rows with `available_at <= clock_time`. Warm-up values remain null; they are never backfilled from future observations.

- [ ] **Step 3: Add runtime state tests**

Prove entry count, holding minutes, cooldown, last signal, and session reset are isolated by `(strategy_id, symbol, session_date)`. A rejected order does not count as an entry; a filled opening order does.

- [ ] **Step 4: Implement runtime state machine**

Allowed states: `FLAT`, `ENTRY_PENDING`, `LONG`, `EXIT_PENDING`, `COOLDOWN`, `SESSION_CLOSED`. Illegal transitions raise a typed engine error and emit an audit event.

- [ ] **Step 5: Run and commit**

```powershell
python -m pytest tests/unit/strategy/test_features.py tests/integration/backtest/test_engine_timing.py -q
git add src/us_intraday_lab/strategy tests/unit/strategy/test_features.py tests/integration/backtest/test_engine_timing.py
git commit -m "feat(strategy): compute completed-bar features causally"
```

## Task 4: Implement Cost, Fill, and Portfolio Models

**Files:**
- Create: `src/us_intraday_lab/backtest/__init__.py`
- Create: `src/us_intraday_lab/backtest/costs.py`
- Create: `src/us_intraday_lab/backtest/fills.py`
- Create: `src/us_intraday_lab/backtest/portfolio.py`
- Test: `tests/unit/backtest/test_costs.py`
- Test: `tests/unit/backtest/test_fills.py`
- Test: `tests/unit/backtest/test_portfolio.py`

- [ ] **Step 1: Encode the three cost scenarios in failing tests**

Keep scenario parameters in a versioned checked-in YAML or frozen Python model. Tests must assert:

- optimistic cost is positive;
- base cost is greater than optimistic;
- stress cost is greater than base;
- `1.5x` cost evaluation scales every variable execution-cost component;
- no promotable scenario has zero commission, zero spread, and zero slippage simultaneously.

Do not invent final bps in tests silently. Copy the exact values from the approved design configuration created during this task and document the source/assumption beside each value.

- [ ] **Step 2: Write deterministic market and limit fill tests**

Market orders become eligible at the next minute-bar open plus scenario slippage. Limit orders fill only when the eligible minute range crosses the price, using a conservative price when both favorable and unfavorable paths are possible. Orders cannot fill on their signal bar.

- [ ] **Step 3: Implement integer-share portfolio accounting**

The portfolio must enforce:

- cash cannot become negative;
- quantity is a positive integer;
- at most 3 concurrent positions;
- no short position;
- realized and unrealized P&L reconcile to equity;
- rejected or partial fills update reservations correctly;
- the end-of-day liquidation is marked separately from strategy exits.

- [ ] **Step 4: Add property-style accounting cases**

Parameterize buy, partial fill, cancel remainder, sell, rejection, and forced close. For every event sequence:

```python
assert portfolio.equity == pytest.approx(
    portfolio.cash + sum(position.market_value for position in portfolio.positions)
)
assert all(position.quantity >= 0 for position in portfolio.positions)
```

- [ ] **Step 5: Run and commit**

```powershell
python -m pytest tests/unit/backtest/test_costs.py tests/unit/backtest/test_fills.py tests/unit/backtest/test_portfolio.py -q
git add src/us_intraday_lab/backtest tests/unit/backtest
git commit -m "feat(backtest): model fills costs and portfolio accounting"
```

## Task 5: Build the Event-Driven Backtest Engine

**Files:**
- Create: `src/us_intraday_lab/backtest/clock.py`
- Create: `src/us_intraday_lab/backtest/engine.py`
- Create: `src/us_intraday_lab/backtest/metrics.py`
- Extend: `src/us_intraday_lab/cli.py`
- Test: `tests/unit/backtest/test_clock.py`
- Test: `tests/unit/backtest/test_metrics.py`
- Test: `tests/integration/backtest/test_engine_timing.py`
- Test: `tests/integration/backtest/test_determinism.py`

- [ ] **Step 1: Write a failing golden-path integration test**

Use synthetic 1-minute and 15-minute bars that force one entry and one exit. Assert the ordered event sequence:

```text
BAR_CLOSED_15M
SIGNAL_ENTER_LONG
ORDER_INTENT_CREATED
ORDER_ELIGIBLE
ORDER_FILLED
POSITION_OPENED
SIGNAL_EXIT_LONG
ORDER_INTENT_CREATED
ORDER_FILLED
POSITION_CLOSED
SESSION_FINALIZED
```

Assert signal time `<` eligible time `<=` fill time and no position remains after close.

- [ ] **Step 2: Implement the engine loop**

For each official session:

1. advance the 1-minute clock;
2. make newly completed 15-minute features visible;
3. evaluate compiled rules once per feature boundary;
4. create idempotent intents;
5. process eligible orders against the current minute;
6. mark positions and equity;
7. force cancellation and liquidation before the configured close buffer;
8. persist events and trades before producing metrics.

- [ ] **Step 3: Implement metrics without promotion decisions**

Compute net return, annualized volatility where meaningful, Sharpe with explicit sampling convention, maximum drawdown, profit factor, win rate, expectancy, trade count, exposure, turnover, cost paid, and P&L by symbol/session. Metrics are descriptive; Plan 3 owns gates.

- [ ] **Step 4: Add deterministic identifiers and output hashing**

The run ID is derived from canonical JSON of `BacktestJob`. Run twice in separate processes and assert identical trade/event/result content hashes. Wall-clock timestamps may appear only in outer metadata excluded from deterministic hashes.

- [ ] **Step 5: Add CLI**

```text
intraday-lab backtest run \
  --strategy <strategy.json> \
  --dataset-id <accepted-id> \
  --initial-cash 25000 \
  --root <repo>
```

The command writes ignored artifacts under `artifacts/backtests/<run-id>/` and prints the result JSON path.

- [ ] **Step 6: Run Plan 2 acceptance**

```powershell
python -m pytest tests/unit/strategy tests/unit/backtest tests/integration/backtest -q
ruff check .
ruff format --check .
python -m mypy src
intraday-lab backtest run --strategy tests/fixtures/strategies/valid_momentum_pullback.json --dataset-id <accepted-id> --initial-cash 25000 --root G:\us-intraday-lab
```

Expected: all checks pass; the run produces three nonzero-cost scenario results, a full audit event log, and zero overnight positions.

- [ ] **Step 7: Commit**

```powershell
git add src/us_intraday_lab/backtest src/us_intraday_lab/cli.py tests/unit/backtest tests/integration/backtest
git commit -m "feat(backtest): add deterministic event-driven engine"
```

## Plan 2 Completion Criteria

- [ ] Malformed or unsafe DSL fails before compilation and carries stable reason codes.
- [ ] No user-controlled string reaches code evaluation, dynamic import, file access, or SQL construction.
- [ ] Feature availability and order eligibility tests prove the next-minute rule.
- [ ] Market and limit fills are deterministic and cost-scenario-specific.
- [ ] Cash, equity, realized P&L, positions, and costs reconcile after every event sequence.
- [ ] Every session ends flat and every order/position transition appears in the append-only event log.
- [ ] Two clean processes produce identical deterministic hashes for the same job.
- [ ] All tests, Ruff, formatting, and mypy pass.
