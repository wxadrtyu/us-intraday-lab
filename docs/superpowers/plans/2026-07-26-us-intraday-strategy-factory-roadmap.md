# US Intraday Strategy Factory Implementation Roadmap

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a local, auditable system that imports the existing US minute-bar archive, generates constrained long-only strategies, validates them with event-driven backtests, and runs the survivors in an Alpaca IEX paper account.

**Architecture:** Build one Python monorepo with explicit package boundaries and versioned Pydantic contracts. Complete four plans in dependency order; each plan must leave a runnable vertical slice and green tests before the next plan begins.

**Tech Stack:** Python 3.12, Pydantic 2, PyArrow/Parquet, DuckDB, SQLite WAL, pandas, NumPy, exchange-calendars, Alpaca-py, Typer, pytest, Ruff, mypy.

## Global Constraints

- Historical decisions come from `docs/superpowers/specs/2026-07-26-us-intraday-strategy-factory-design.md`.
- Production paper symbols are `SPY`, `QQQ`, and `IWM`; the other archived liquid symbols are robustness-only.
- Strategies are long-only, regular-hours-only, unlevered, and flat before the close.
- Signals use a completed 15-minute bar; the earliest execution input is the next 1-minute bar.
- Every promotion result must include optimistic, base, and stress cost scenarios. Zero-cost results cannot promote a strategy.
- Historical split is chronological `70% / 20% / 10%`; tuning can see only the first 70%.
- Hard gates are: positive base and `1.5x` cost returns, at least 100 trades, maximum drawdown at most 8%, profit factor at least 1.15, at least 60% profitable walk-forward windows, parameter stability, no ETF contributing more than 70% of profit, stable start-date checks, and a passed null test.
- Paper ranking starts only after 30 paper trading days and 50 closed trades.
- Capacity limits are 20 observing, 5 ranked, and 3 leaders.
- Paper-account reference balance is `$25,000`; reports also replay `$5,000` and `$10,000` feasibility.
- There is no real-money broker endpoint, switch, credential setting, or release task.
- Raw bars, generated features, databases, broker credentials, and generated reports stay outside Git.
- Reused code is copied selectively with provenance; the old repository is never added as a runtime dependency.
- A failed quality, safety, reconciliation, or risk gate must stop the affected run instead of silently falling back.
- User-facing reports are Chinese; code, schemas, identifiers, and machine-readable reason codes are English.

## Plan Sequence

1. [Data Foundation Plan](2026-07-26-intraday-data-foundation-plan.md)
   - Creates packaging, shared contracts, archive import, canonical bars, quality gates, Parquet partitions, and the DuckDB catalog.
   - Exit artifact: a reproducible dataset snapshot with hashes and a passing data acceptance command.
2. [Strategy DSL and Backtest Plan](2026-07-26-strategy-dsl-backtest-plan.md)
   - Creates the constrained DSL, compiler, feature timing, event-driven engine, orders, fills, and accounting.
   - Exit artifact: a deterministic hand-authored strategy backtest over the imported dataset.
3. [Strategy Factory and Validation Plan](2026-07-26-strategy-factory-validation-plan.md)
   - Creates structured hypothesis intake, deterministic variants, experiment lineage, hard gates, null tests, registry, and research reports.
   - Exit artifact: one command that generates, tests, rejects/promotes, and reports a strategy family without allowing AI-authored executable code.
4. [Paper Execution and Reporting Plan](2026-07-26-paper-execution-reporting-plan.md)
   - Creates Alpaca IEX ingestion, SQLite state, reconciliation, idempotent orders, risk controls, paper lifecycle, forward ranking, and Chinese daily reports.
   - Exit artifact: a restart-safe paper session whose injected-failure tests prove it cannot place real-money orders or hold overnight.

## Integration Checkpoints

- [ ] After Plan 1, tag the dataset contract and freeze the bootstrap snapshot identifier used by later test fixtures.
- [ ] After Plan 2, record a golden backtest result and verify identical output from two clean processes.
- [ ] After Plan 3, run an end-to-end research cycle and confirm every leaderboard row links to immutable strategy, dataset, code, and cost-model identifiers.
- [ ] After Plan 4, run a full simulated market day with disconnect, duplicate-event, rejected-order, restart, and closeout fault injection.
- [ ] Before any paper session, run the complete suite: `python -m pytest`, `ruff check .`, `ruff format --check .`, and `python -m mypy src`.

## Explicit Non-Goals

- Sub-second or colocated high-frequency trading.
- Options, futures, short selling, leverage, extended-hours trading, or overnight positions.
- A free-form Python strategy generator.
- Kafka, Kubernetes, microservice deployment, or a distributed feature store.
- Automatic retraining or exploration on a timer; research starts only when the user runs it.
- Automatic conversion from paper trading to real money.
