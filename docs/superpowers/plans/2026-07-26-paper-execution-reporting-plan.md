# Paper Execution and Reporting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run promoted strategies automatically in an Alpaca IEX paper account with restart-safe state, idempotent orders, strict long-only/no-overnight risk controls, forward-only ranking, and understandable Chinese daily reports.

**Architecture:** A paper-only broker adapter and IEX market-data adapter feed a session service built around an exchange calendar. SQLite WAL stores events, orders, positions, checkpoints, and lifecycle evidence. Startup always reconciles broker truth before enabling orders. A separate evaluator ranks eligible paper strategies after hard age/trade gates and renders reports from stored events.

**Tech Stack:** Python 3.12, Pydantic 2, Alpaca-py, exchange-calendars, SQLite WAL, pandas, PyArrow, Jinja2, Typer, pytest, Ruff, mypy.

## Global Constraints

- Complete Plans 1 through 3 first.
- The only supported broker environment is Alpaca paper. Base URL and account status must prove paper mode at startup.
- Do not implement a live base URL, live credential names, live account mode, live order adapter, or a flag that bypasses the paper check.
- Market data feed is Alpaca IEX. SIP may be queried only by an explicit diagnostic command and never mixed into production paper bars.
- Production symbols are exactly `SPY`, `QQQ`, and `IWM`.
- Long-only, integer shares, no leverage, no overnight, regular-hours-only.
- Maximum 3 entries per strategy per day and maximum 3 account positions.
- Reference account balance is `$25,000`; strategy feasibility also replays `$5,000` and `$10,000`.
- Signals use completed 15-minute bars and earliest next-minute execution.
- Capacity is 20 observing, 5 ranked, and 3 leaders.
- A strategy needs at least 30 paper trading days and 50 closed paper trades before ranking.
- Hard paper eligibility gates run before forward-quality ranking.
- A disconnect, stale feed, clock uncertainty, reconciliation mismatch, database failure, rejected closeout, or breached risk invariant disables new entries.
- At session end, cancel opening orders, submit exits, verify flatness, and escalate visibly if the broker still reports exposure.
- All order intents and broker submissions are idempotent across retries and restarts.
- Paper reports must never imply that simulated profit is guaranteed or equivalent to live execution.

---

## File Structure

```text
src/us_intraday_lab/
  contracts/
    market.py
    paper.py
    reports.py
  paper/
    broker.py
    alpaca_paper.py
    market_data.py
    store.py
    reconciliation.py
    risk.py
    sizing.py
    session.py
    recovery.py
  forward/
    eligibility.py
    evaluator.py
    ranking.py
    lifecycle.py
  reporting/
    paper_daily.py
    strategy_detail.py
    templates/paper_daily_zh.md.j2
    templates/strategy_detail_zh.md.j2
tests/
  fakes/
    broker.py
    market_data.py
  unit/paper/
    test_paper_boundary.py
    test_store.py
    test_reconciliation.py
    test_risk.py
    test_sizing.py
    test_recovery.py
  unit/forward/
    test_eligibility.py
    test_ranking.py
    test_lifecycle.py
  integration/paper/
    test_session.py
    test_fault_injection.py
    test_end_of_day.py
  integration/reporting/
    test_paper_daily.py
```

`broker.py` defines the minimal interface. `alpaca_paper.py` is the only external-order implementation. `store.py` owns durable state. `reconciliation.py` compares local and broker truth. `risk.py` can veto intents but cannot create them. `forward` reads completed paper evidence and writes lifecycle decisions through the registry.

## Task 1: Define Paper Events and a Broker Interface That Cannot Go Live

**Files:**
- Modify: `pyproject.toml`
- Create: `src/us_intraday_lab/contracts/market.py`
- Create: `src/us_intraday_lab/contracts/paper.py`
- Create: `src/us_intraday_lab/paper/broker.py`
- Create: `src/us_intraday_lab/paper/alpaca_paper.py`
- Create: `tests/fakes/broker.py`
- Test: `tests/unit/paper/test_paper_boundary.py`

- [ ] **Step 1: Write failing paper-boundary tests**

Assert construction fails unless:

- configured URL equals the approved Alpaca paper endpoint;
- the broker account response reports a paper account;
- credentials come from paper-only environment variable names;
- account trading is not blocked.

Search the public configuration model and CLI help to assert there is no `live`, `real`, `production broker`, or alternate base-URL option.

- [ ] **Step 2: Define minimal broker operations**

Add `alpaca-py>=0.42,<1` as a direct runtime dependency in `pyproject.toml`, then reinstall with `python -m pip install -e ".[dev]"`. Record the resolved SDK version in the lock file and paper-session metadata.

```python
class PaperBroker(Protocol):
    def account(self) -> BrokerAccount: ...
    def clock(self) -> BrokerClock: ...
    def open_orders(self) -> tuple[BrokerOrder, ...]: ...
    def positions(self) -> tuple[BrokerPosition, ...]: ...
    def submit(self, intent: OrderIntent) -> BrokerOrder: ...
    def cancel(self, broker_order_id: str) -> BrokerOrder: ...
```

No generic arbitrary request method. No endpoint mutation after construction.

- [ ] **Step 3: Define market and paper contracts**

Create frozen, versioned models for `MarketBarClosed`, `BrokerAccount`, `BrokerClock`, `BrokerOrder`, `BrokerPosition`, `PositionSnapshot`, `PaperCheckpoint`, `RiskDecision`, and `DailyPaperReport`. Every timestamp is aware UTC and every market bar records provider/feed.

- [ ] **Step 4: Implement the Alpaca paper adapter**

Map only the protocol operations. Verify the paper endpoint and account on construction. Convert SDK objects immediately into internal contracts; do not leak SDK types into business logic. Never log credentials or authorization headers.

- [ ] **Step 5: Implement the deterministic fake broker**

The fake supports accept, reject, partial fill, delayed fill, disconnect, stale clock, and forced broker-side position mutation. It records submitted idempotency keys.

- [ ] **Step 6: Run and commit**

```powershell
python -m pytest tests/unit/paper/test_paper_boundary.py -q
git add src/us_intraday_lab/contracts src/us_intraday_lab/paper tests/fakes tests/unit/paper/test_paper_boundary.py
git commit -m "feat(paper): enforce paper-only broker boundary"
```

## Task 2: Persist Events, Orders, Positions, and Checkpoints in SQLite WAL

**Files:**
- Create: `src/us_intraday_lab/paper/store.py`
- Test: `tests/unit/paper/test_store.py`

- [ ] **Step 1: Write transactional-store tests**

Test:

- WAL and foreign keys are enabled;
- order intent, event, and checkpoint commit atomically;
- a duplicate idempotency key with identical content returns the original record;
- the same key with different content fails;
- concurrent readers see only committed state;
- an injected write failure rolls back the entire transaction;
- append-only event rows cannot be updated or deleted through the store API.

- [ ] **Step 2: Create the schema**

Tables:

```text
paper_sessions
market_events
order_intents
order_events
position_snapshots
risk_decisions
strategy_session_state
paper_checkpoints
reconciliation_runs
incident_events
```

Use unique constraints on provider event IDs and order idempotency keys. Store canonical JSON and content hashes for replay.

- [ ] **Step 3: Implement atomic append APIs**

All writes use explicit `BEGIN IMMEDIATE`, commit, rollback, a busy timeout, and typed storage errors. A storage error sets the in-memory session circuit breaker before it propagates.

- [ ] **Step 4: Run and commit**

```powershell
python -m pytest tests/unit/paper/test_store.py -q
git add src/us_intraday_lab/paper/store.py tests/unit/paper/test_store.py
git commit -m "feat(paper): persist restart-safe paper state"
```

## Task 3: Reconcile Broker Truth Before Enabling Orders

**Files:**
- Create: `src/us_intraday_lab/paper/reconciliation.py`
- Create: `src/us_intraday_lab/paper/recovery.py`
- Test: `tests/unit/paper/test_reconciliation.py`
- Test: `tests/unit/paper/test_recovery.py`

- [ ] **Step 1: Write reconciliation cases**

Cover:

- clean flat startup;
- matching open position and order;
- broker has a position absent locally;
- local state has a position absent at broker;
- quantity mismatch;
- unknown broker order;
- locally pending order already filled at broker;
- duplicate market event after restart.

Only clean or safely recoverable cases may enable new entries. Exposure mismatches must enter `RECONCILIATION_BLOCKED`.

- [ ] **Step 2: Implement startup sequence**

```text
OPEN_STORE
VERIFY_SCHEMA
VERIFY_PAPER_BROKER
FETCH_BROKER_CLOCK
FETCH_ACCOUNT
FETCH_OPEN_ORDERS
FETCH_POSITIONS
REPLAY_LOCAL_EVENTS
COMPARE
PERSIST_RECONCILIATION
ENABLE_EXITS
ENABLE_ENTRIES_IF_CLEAN
```

Exits may be enabled before entries to reduce risk. Never infer broker truth from local state.

- [ ] **Step 3: Implement checkpoint recovery**

Resume after the latest verified checkpoint, replay later events by unique provider ID, and rebuild strategy/session state. The resulting state hash must match a clean full replay.

- [ ] **Step 4: Add idempotent-order key construction**

Key input:

```text
paper_session_id
strategy_id
symbol
signal_available_at
action
entry_sequence
```

Retrying the same intent reuses the key; a distinct signal or action cannot collide.

- [ ] **Step 5: Run and commit**

```powershell
python -m pytest tests/unit/paper/test_reconciliation.py tests/unit/paper/test_recovery.py -q
git add src/us_intraday_lab/paper/reconciliation.py src/us_intraday_lab/paper/recovery.py tests/unit/paper
git commit -m "feat(paper): reconcile and recover before trading"
```

## Task 4: Enforce Risk, Sizing, and Session-Close Invariants

**Files:**
- Create: `src/us_intraday_lab/paper/risk.py`
- Create: `src/us_intraday_lab/paper/sizing.py`
- Test: `tests/unit/paper/test_risk.py`
- Test: `tests/unit/paper/test_sizing.py`
- Test: `tests/integration/paper/test_end_of_day.py`

- [ ] **Step 1: Write a complete risk-decision table**

Reject new entries when any condition holds:

- symbol is not in the production trio;
- outside regular hours or inside the closeout buffer;
- feed or broker clock is stale;
- reconciliation is not clean;
- storage circuit breaker is open;
- account already has 3 positions;
- strategy already entered 3 times;
- strategy is paused/retired/not in an enabled paper state;
- order would require fractional shares, negative cash, margin, leverage, or short exposure;
- daily/account/strategy loss limit from configuration is breached;
- duplicate or conflicting intent exists.

Every decision includes a stable reason code and observed values.

- [ ] **Step 2: Implement conservative integer sizing**

Sizing consumes available cash, latest eligible reference price, stop distance, strategy risk allocation, and account caps. Floor to integer shares. Return `NO_FEASIBLE_INTEGER_POSITION` rather than rounding up or borrowing.

- [ ] **Step 3: Add balance-feasibility replays**

For every candidate intent, calculate feasible quantity for `$5,000`, `$10,000`, and `$25,000` reference balances. These are report diagnostics; the broker account truth controls actual sizing.

- [ ] **Step 4: Write session-close integration tests**

At the closeout boundary:

1. stop new entries;
2. cancel opening orders;
3. wait for terminal cancellation/fill events;
4. submit exits for every remaining long position;
5. poll broker positions until flat or timeout;
6. persist final snapshot and incident if not flat.

Inject a rejected exit and assert repeated idempotent retries plus a visible `OVERNIGHT_RISK_INCIDENT`; never mark the session clean while exposure remains.

- [ ] **Step 5: Implement and commit**

```powershell
python -m pytest tests/unit/paper/test_risk.py tests/unit/paper/test_sizing.py tests/integration/paper/test_end_of_day.py -q
git add src/us_intraday_lab/paper tests/unit/paper tests/integration/paper/test_end_of_day.py
git commit -m "feat(paper): enforce sizing risk and flat close"
```

## Task 5: Consume Alpaca IEX Bars and Run the Automated Paper Session

**Files:**
- Create: `src/us_intraday_lab/paper/market_data.py`
- Create: `src/us_intraday_lab/paper/session.py`
- Extend: `src/us_intraday_lab/cli.py`
- Create: `tests/fakes/market_data.py`
- Test: `tests/integration/paper/test_session.py`
- Test: `tests/integration/paper/test_fault_injection.py`

- [ ] **Step 1: Write market-data tests**

Assert:

- only `SPY`, `QQQ`, and `IWM` subscriptions are accepted;
- provider/feed are `alpaca/iex`;
- duplicate and out-of-order bar events are deduplicated/reordered within a bounded buffer;
- a gap or stale stream opens the entry circuit breaker;
- 15-minute bars align to the same calendar rules as historical data;
- provider-transition diagnostics remain separate from paper production bars.

- [ ] **Step 2: Implement closed-bar aggregation**

Persist 1-minute bars, aggregate session-anchored 15-minute bars, and emit `MarketBarClosed` only after the interval is complete. Compare the schema and feature versions to Plans 1 and 2 at startup.

- [ ] **Step 3: Write automated-session golden test**

With fake time, fake bars, fake broker, one enabled strategy, and SQLite:

- startup reconciles;
- a completed 15-minute bar creates a signal;
- the intent is eligible no earlier than the next minute;
- risk approves and the broker sees one idempotent submission;
- fills update positions and strategy state;
- a restart does not duplicate the order;
- closeout ends flat.

- [ ] **Step 4: Implement the session service**

The main loop handles broker/order events and market events, checkpoints after durable transitions, sends only validated intents, and emits health status. Research orchestration never runs inside this process.

- [ ] **Step 5: Add injected-failure scenarios**

Test disconnect, stale bars, database write failure, broker timeout after accepting an order, duplicate order update, partial fill, restart during pending order, rejected exit, and local/broker position mismatch. In all cases assert no unintended new entry and no duplicate broker submission.

- [ ] **Step 6: Add CLI**

```text
intraday-lab paper preflight --root G:\us-intraday-lab
intraday-lab paper run --root G:\us-intraday-lab
intraday-lab paper reconcile --root G:\us-intraday-lab
intraday-lab paper closeout --root G:\us-intraday-lab
intraday-lab data diagnose-sip-difference --session YYYY-MM-DD --root G:\us-intraday-lab
```

`preflight` proves paper mode, calendar/session status, production symbols, strategy capacity, schema versions, clean reconciliation, and writable ignored state paths. It never submits an order.

- [ ] **Step 7: Run and commit**

```powershell
python -m pytest tests/integration/paper -q
git add src/us_intraday_lab/paper src/us_intraday_lab/cli.py tests/fakes tests/integration/paper
git commit -m "feat(paper): run automated Alpaca IEX paper sessions"
```

## Task 6: Evaluate Forward Evidence and Enforce Paper Lifecycle

**Files:**
- Create: `src/us_intraday_lab/forward/__init__.py`
- Create: `src/us_intraday_lab/forward/eligibility.py`
- Create: `src/us_intraday_lab/forward/evaluator.py`
- Create: `src/us_intraday_lab/forward/ranking.py`
- Create: `src/us_intraday_lab/forward/lifecycle.py`
- Test: `tests/unit/forward/test_eligibility.py`
- Test: `tests/unit/forward/test_ranking.py`
- Test: `tests/unit/forward/test_lifecycle.py`

- [ ] **Step 1: Write paper eligibility tests**

Before ranking, require:

- at least 30 distinct completed paper trading days;
- at least 50 closed paper trades;
- no unresolved reconciliation or overnight-risk incident;
- current lifecycle state is observing;
- minimum data completeness and execution-quality checks pass;
- capacity has not been exceeded.

Use broker-confirmed fills, not backtest or shadow fills.

- [ ] **Step 2: Implement quality ranking**

Rank only eligible strategies using stored forward evidence: net return, drawdown, profit factor, expectancy, day/week consistency, cost/slippage realization, symbol concentration, and divergence from historical expectations. Store component values and weights. Resolve ties by immutable strategy ID.

- [ ] **Step 3: Write lifecycle and capacity tests**

Allowed states:

```text
paper_shadow -> paper_observing
paper_observing -> paper_ranked
paper_ranked -> leader
paper_observing|paper_ranked|leader -> paused
paused -> paper_observing
any non-retired state -> review
review -> paused|retired|paper_observing
```

Enforce maximum 20 observing, 5 ranked, and 3 leaders transactionally. Demotion never deletes evidence.

- [ ] **Step 4: Implement evaluator and lifecycle writes**

Hard eligibility/gates run first, ranking second, capacity transition third. A lower-ranked incumbent is demoted only through an explicit registry event with evidence links.

- [ ] **Step 5: Run and commit**

```powershell
python -m pytest tests/unit/forward -q
git add src/us_intraday_lab/forward tests/unit/forward
git commit -m "feat(forward): rank eligible paper strategies"
```

## Task 7: Render Daily and Strategy-Level Chinese Reports

**Files:**
- Create: `src/us_intraday_lab/reporting/paper_daily.py`
- Create: `src/us_intraday_lab/reporting/strategy_detail.py`
- Create: `src/us_intraday_lab/reporting/templates/paper_daily_zh.md.j2`
- Create: `src/us_intraday_lab/reporting/templates/strategy_detail_zh.md.j2`
- Extend: `src/us_intraday_lab/cli.py`
- Test: `tests/integration/reporting/test_paper_daily.py`

- [ ] **Step 1: Write report evidence tests**

Render from a fixed store and assert each displayed P&L, trade count, drawdown, status, incident, and ranking component equals stored evidence. Reports cannot recalculate broker fills from bars.

- [ ] **Step 2: Implement daily report sections**

Chinese report:

```text
账户与会话状态
今日收益与累计收益
持仓与收盘平仓结果
订单、成交、拒单与滑点
策略状态变化
观察/排名/领导者列表
数据与系统健康
异常与待处理事项
5千/1万/2.5万美元可执行性
风险声明
```

- [ ] **Step 3: Implement strategy detail**

Show immutable strategy definition, historical split/gates, paper age/trades, forward metrics, symbol/day contribution, realized execution quality, lifecycle events, incidents, and divergence from historical expectations.

- [ ] **Step 4: Add report CLI**

```text
intraday-lab report paper-daily --session YYYY-MM-DD --root G:\us-intraday-lab
intraday-lab report strategy --strategy-id <id> --root G:\us-intraday-lab
```

Generated files go under ignored `reports/generated/`.

- [ ] **Step 5: Run the full Plan 4 acceptance**

```powershell
python -m pytest tests/unit/paper tests/unit/forward tests/integration/paper tests/integration/reporting -q
ruff check .
ruff format --check .
python -m mypy src
intraday-lab paper preflight --root G:\us-intraday-lab
```

With paper credentials present, preflight must exit 0 without submitting an order. Without credentials, it must fail with a clear paper-credential reason and still submit no order.

- [ ] **Step 6: Commit**

```powershell
git add src/us_intraday_lab/reporting src/us_intraday_lab/cli.py tests/integration/reporting
git commit -m "feat(reporting): explain paper performance in Chinese"
```

## Plan 4 Completion Criteria

- [ ] Source and CLI review confirms there is no route to a real-money endpoint.
- [ ] Startup reconciliation blocks entries on every unresolved mismatch.
- [ ] Duplicate events, retries, and restarts cannot duplicate an order.
- [ ] Every approved entry respects symbol, session, position, entry-count, cash, integer-share, and lifecycle limits.
- [ ] End-of-day tests finish flat or emit an unresolved high-severity incident without claiming success.
- [ ] Paper ranking cannot begin before 30 days and 50 trades.
- [ ] Capacity remains at most 20 observing, 5 ranked, and 3 leaders.
- [ ] Daily reports reconcile exactly to stored broker-confirmed events.
- [ ] Full fault-injection, unit, integration, Ruff, formatting, and mypy gates pass.
