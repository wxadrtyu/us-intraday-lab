# US Intraday Strategy Factory Design

- Date: 2026-07-26
- Status: Approved in conversation; awaiting review of this written specification
- Repository: `G:\us-intraday-lab`
- Scope: US equity intraday research, backtesting, and automated paper-forward trading

## 1. Purpose

Build an independent US intraday strategy factory that can:

1. use AI to propose economically motivated strategy hypotheses;
2. express strategies in a constrained, auditable DSL;
3. generate and test programmatic variants;
4. eliminate weak or unrealistic candidates through deterministic validation;
5. run qualified strategies automatically in Alpaca Paper;
6. rank strategies primarily by paper-forward return quality; and
7. pause or retire strategies whose forward performance or operational integrity degrades.

The project is intended to find promising paper-trading strategies. It does not promise profit and does not contain a real-money execution path.

## 2. Confirmed Product Decisions

- The new repository remains operationally independent from `G:\quant-agent-team-us`.
- The architecture is service-oriented, but the first release runs locally in one Git repository rather than as a distributed cluster.
- Research runs are started on demand. There is no automatic daily, weekly, or monthly strategy-generation schedule.
- The paper execution process may remain running during US market hours after the user starts it.
- Production paper symbols are `SPY`, `QQQ`, and `IWM`.
- The other 60 liquid symbols in the inherited minute snapshot form a robustness-only research panel.
- Strategies are long-only, may stay in cash, trade only regular hours, and close all positions before the session ends.
- The strategy factory is open-ended but constrained by a DSL.
- AI proposes hypotheses and DSL prototypes; deterministic software generates variants, backtests, validates, promotes, ranks, pauses, and retires them.
- Historical candidates must pass hard gates before ranking.
- Final priority is based on forward paper performance quality, not historical backtest return alone.
- No live-money API endpoint or configuration is implemented.

## 3. Existing Assets and Reuse Decision

### 3.1 Historical data that can be reused

The old repository contains `data/us_stock_data.tar.gz`. Direct inspection on 2026-07-26 found:

- source tag: `tiingo_iex`;
- one-minute US equity rows: 1,418,418;
- symbols: 63, including `SPY`, `QQQ`, and `IWM`;
- coverage: 2025-06-23 13:30 UTC through 2026-07-02 19:59 UTC;
- 3,628 complete symbol-sessions with 390 regular-session bars;
- 9 slightly incomplete symbol-sessions;
- no consecutive duplicate symbol/timestamp keys;
- no missing OHLCV values in the one-minute file;
- no weekend or outside-regular-session rows.

This data is suitable as a bootstrap research snapshot, subject to licensing/provenance review and repeatable import validation.

### 3.2 Concepts and small utilities worth reusing

- DuckDB-based research analysis;
- immutable research-run manifests;
- rolling walk-forward validation;
- sealed holdout discipline;
- randomized/null benchmarks;
- deterministic metrics such as drawdown and information ratio;
- test patterns for cost, holdout, and data-quality behavior.

Reusable code must be copied into the new repository only after focused review and new tests. The new repository must not import the old project as a runtime Python dependency.

### 3.3 Components that must not be reused as the new core

- the old daily cross-sectional backtest engines;
- `paper_trade.py`, which produces a latest signal but is not an order simulator;
- the fixed-basis-point cost model as the sole execution model;
- the old strategy registry, research database, or monitoring pool;
- hard-coded paths and temporary operational scripts;
- precomputed intraday indicators or higher-timeframe bars from the archive.

The one-minute file is the canonical reusable historical input. Higher timeframes and indicators are rebuilt in the new project.

## 4. Architecture

The system uses service boundaries inside one local Python repository.

### 4.1 Research Orchestrator

- accepts an on-demand exploration request;
- creates a unique, resumable `research_run_id`;
- invokes hypothesis generation, DSL validation, variant generation, backtest workers, validation, and candidate registration;
- records progress and failure reasons;
- cannot submit paper orders.

### 4.2 Data Service

- imports the old minute snapshot read-only;
- records source hashes, schema, coverage, and quality results;
- acquires and normalizes subsequent Alpaca IEX data;
- creates deterministic 5-minute and 15-minute bars from canonical 1-minute bars;
- publishes versioned dataset manifests.

### 4.3 Strategy Factory

- accepts structured AI hypotheses;
- compiles and validates DSL strategies;
- generates bounded parameter and rule variants;
- canonicalizes and deduplicates semantically identical strategies;
- emits immutable strategy definitions.

### 4.4 Backtest Workers

- run an event-driven minute simulator;
- evaluate signal logic on closed bars;
- execute no earlier than the next eligible one-minute interval;
- model market and limit orders, cash use, spread, slippage, latency, partial fills, cancellation, and rejection;
- support parallel tasks without writing paper-account state.

### 4.5 Validation and Registry Service

- applies historical hard gates, walk-forward validation, sealed holdout, perturbation tests, and null benchmarks;
- freezes a qualified strategy with its DSL, parameters, lineage, data version, cost-model version, and Git commit;
- controls automatic promotion into paper shadow and paper observation;
- retains failed and retired strategies rather than deleting evidence.

### 4.6 Paper Execution Service

- is a separate long-running process;
- loads only frozen strategy bundles;
- consumes Alpaca IEX real-time data;
- submits orders only to Alpaca Paper;
- persists order, fill, position, heartbeat, and recovery state;
- stops new entries when data, account, or risk state is unsafe.

### 4.7 Forward Evaluator and Reporting

- reconciles intended orders, Alpaca Paper fills, and a conservative local fill model;
- maintains separate historical, observing, and ranked-forward leaderboards;
- produces Chinese research-run, daily paper, and strategy-detail reports;
- automatically pauses, downgrades, or retires failing strategies.

## 5. Cross-Service Contracts

The first release uses versioned Pydantic/JSON contracts rather than a message broker.

Core contracts include:

- `DatasetManifest`
- `HypothesisProposal`
- `StrategyDefinition`
- `StrategyBundle`
- `BacktestJob`
- `BacktestResult`
- `ValidationDecision`
- `MarketBarClosed`
- `OrderIntent`
- `OrderEvent`
- `PositionSnapshot`
- `DailyPaperReport`

Batch services exchange job manifests and immutable artifacts. The paper service uses a durable local event log. Contract versions are explicit; incompatible versions fail closed.

Kafka, Kubernetes, and remote microservice deployment are deferred. Interfaces must allow later replacement of the local transport without changing strategy semantics.

## 6. Data Design

### 6.1 Bootstrap import

The importer reads:

`G:\quant-agent-team-us\data\us_stock_data.tar.gz`

It extracts only required one-minute prices, symbol metadata, and optional diagnostic microstructure summaries into the new data lake. The importer records:

- source archive SHA-256;
- member-file hash;
- schema;
- row and symbol counts;
- minimum and maximum timestamps;
- duplicates, gaps, nulls, and outliers;
- import code Git commit.

Large data files are not committed to Git. Manifests and validation reports are committed or stored as versioned run artifacts.

### 6.2 Canonical minute-bar schema

- `symbol`
- `event_time_utc`
- `session_date_ny`
- `bar_size`
- `open`
- `high`
- `low`
- `close`
- `volume`
- `trade_count`, when available
- `vwap`, when available
- `source`
- `dataset_version`

Storage is UTC. Session boundaries use `America/New_York`, including daylight saving time, holidays, and half days.

### 6.3 Provider discipline

- bootstrap history: Tiingo IEX snapshot;
- ongoing research history: Alpaca IEX;
- paper real-time feed: Alpaca IEX;
- delayed SIP data: diagnostic comparison only.

Tiingo and Alpaca rows are never silently blended. Before an explicit source transition, their overlap is compared for OHLC, volume, missing bars, and session boundaries. A failed comparison creates separate dataset versions rather than one combined training set.

### 6.4 Storage roles

- Parquet: immutable raw, normalized, and feature snapshots;
- DuckDB: research catalog, dataset views, run metadata, backtest and validation results;
- SQLite in WAL mode: paper orders, events, positions, heartbeats, idempotency keys, and recovery snapshots.

Research workers do not write to the paper-state database. The paper service does not write operational events into the research DuckDB.

### 6.5 Data quality gates

- unique `symbol + event_time_utc + bar_size`;
- positive prices and valid OHLC relationships;
- non-negative volume;
- calendar-aware expected minute counts;
- explicit half-day classification;
- no silent forward-filling of prices;
- closed bars only for strategy evaluation;
- deterministic 5-minute and 15-minute reconstruction;
- explicit provider-transition validation;
- every result linked to a dataset version and checksum.

## 7. Strategy DSL

### 7.1 Supported concepts

- timeframes;
- production or robustness universe;
- long-only side;
- whitelisted OHLCV, VWAP, return, volatility, ATR, moving-average, RSI, opening-range, volume, and market-regime features;
- `all`, `any`, and `not` conditions;
- time, indicator, stop-loss, take-profit, and trailing-stop exits;
- fixed-risk and volatility-aware position sizing;
- maximum positions, entries, exposure, and holding duration;
- regular-session and no-overnight constraints.

### 7.2 Static safety checks

The compiler rejects:

- non-whitelisted features or operators;
- out-of-range parameters;
- references to bars that have not closed;
- future-data references;
- impossible or incomplete entry/exit rules;
- shorting, leverage, or extended-hours trading;
- missing portfolio-risk controls;
- strategies exceeding the configured complexity budget.

The compiled strategy runtime is shared by backtesting and paper execution.

### 7.3 AI proposal contract

AI supplies:

- the market behavior being targeted;
- an economic or behavioral rationale;
- expected market regime;
- expected holding period;
- likely failure conditions;
- a DSL prototype;
- bounded parameter ranges.

AI cannot edit results, lower gates, execute arbitrary generated Python, or directly promote a strategy.

### 7.4 Programmatic variation

The factory may:

- vary parameters within approved ranges;
- substitute indicators inside a category;
- add or remove approved filters;
- compare exit and sizing rules;
- deduplicate normalized DSL fingerprints;
- limit search breadth and strategy complexity.

## 8. Research Pipeline

Each on-demand run performs:

1. AI hypothesis generation;
2. DSL compilation and safety validation;
3. bounded variant generation;
4. canonicalization and deduplication;
5. short smoke backtests;
6. complete realistic-cost backtests;
7. purged walk-forward validation;
8. one-touch sealed holdout;
9. historical shadow check;
10. parameter, cost, fill, and start-date perturbation;
11. randomized/null comparisons;
12. automatic candidate registration;
13. paper shadow;
14. paper observation;
15. ranked forward evaluation.

Runs can pause and resume. Completed variants are content-addressed and are not recomputed unless their strategy, data, code, or execution-model version changes.

## 9. Backtest and Execution Model

### 9.1 Timing

A signal may use a closed 15-minute bar. The earliest eligible execution begins on the next 1-minute interval. Same-bar signal-and-fill behavior is prohibited.

### 9.2 First-release order limits

- market and limit orders;
- integer shares;
- long-only;
- regular session only;
- no leverage or negative cash;
- no overnight positions;
- at most three entries per strategy per day;
- at most three account positions at one time.

### 9.3 Fill models

Market orders use the next eligible reference price plus or minus half-spread and latency slippage.

Limit orders become fill-eligible only after the subsequent price path reaches the limit. Touching a limit does not guarantee a fill. Fill probability and volume participation are conservative and scenario-dependent.

Every candidate is evaluated under:

- optimistic diagnostic execution;
- conservative base execution;
- stress execution with 1.5–2 times base friction and lower limit-fill probability.

Zero-cost results cannot promote a strategy.

### 9.4 Portfolio accounting

The simulator tracks:

- available and reserved cash;
- working orders;
- realized and unrealized profit;
- position cost;
- transaction costs;
- daily equity;
- intraday and total drawdown;
- strategy-level virtual allocations;
- portfolio-level capital competition and duplicate exposure.

The portfolio allocator resolves simultaneous or duplicate signals before orders are sent.

## 10. Historical Validation and Promotion Gates

Chronological allocation:

- 70% development with purged walk-forward validation;
- 20% sealed holdout, touched once per strategy version;
- 10% historical shadow validation.

Default historical promotion gates:

- positive net return under conservative base costs;
- positive net return under 1.5-times cost stress;
- at least 100 completed historical trades;
- maximum drawdown no greater than 8%;
- profit factor at least 1.15;
- profitable in at least 60% of walk-forward windows;
- parameter-neighborhood stability;
- no single ETF contributing more than 70% of total profit;
- stable conclusion under small start-date changes;
- material advantage over randomized/null signals.

Gate configuration is versioned and applies uniformly. A gate cannot be relaxed for an individual candidate.

## 11. Paper Lifecycle and Recovery

### 11.1 Strategy lifecycle

1. `CANDIDATE`: historical validation passed and bundle frozen.
2. `PAPER_SHADOW`: realtime signals run without submitting orders.
3. `PAPER_OBSERVING`: Alpaca Paper orders are submitted; observation requirements are accumulating.
4. `PAPER_RANKED`: minimum forward duration and trades are satisfied.
5. `PAPER_LEADER`: a diversified top-ranked strategy.
6. `PAUSED`: entries are disabled after a risk, data, or operational trigger.
7. `REVIEW_REQUIRED`: automated recovery cannot establish safety.
8. `RETIRED`: permanently removed from active paper trading; evidence remains.

Any strategy change creates a new version that restarts validation.

### 11.2 Startup reconciliation

Before trading, the service:

1. loads its persisted event log;
2. queries Alpaca account, working orders, fills, and positions;
3. rebuilds local state;
4. compares local and remote state;
5. permits new entries only if reconciliation succeeds.

### 11.3 Order idempotency

Every intent receives a deterministic `client_order_id`. Retrying an intent reuses the same ID. The service processes partial fills, fills, cancellations, expirations, and rejections as persistent events.

### 11.4 Session close

- disable new entries at the configured cutoff;
- cancel working entry orders;
- close positions before the session ends;
- reconcile account and local state;
- write an end-of-day snapshot and report.

Failure to flatten or reconcile blocks automatic entry on the next session.

### 11.5 Failure behavior

Data delay, missing bars, or timestamp reversal:

- stop entries;
- cancel eligible working entry orders;
- restore and recompute state;
- never replay an expired signal.

Connectivity loss:

- reconnect with exponential backoff;
- reconcile by REST before resuming streams or orders.

Risk or order anomaly:

- pause an affected strategy for strategy-level triggers;
- activate a global kill switch for account-level exposure or reconciliation failure.

## 12. Forward Ranking

Three leaderboards remain separate:

1. historical candidates;
2. paper-observing strategies;
3. ranked-forward strategies.

A strategy needs at least 30 paper trading days and 50 completed forward trades before entering the formal forward leaderboard.

Eligibility requires:

- positive forward net return;
- drawdown within the active gate;
- no unresolved operational incident;
- no severe loss under the conservative local fill model;
- no extreme dependence on one day or one ETF.

Eligible strategies are ranked using:

- return relative to drawdown;
- forward net return;
- profitable-week share;
- concentration penalties;
- consistency between Alpaca fills and the conservative local fill model;
- recent deterioration.

Capacity limits:

- no more than 20 observing strategies;
- no more than 5 formally ranked strategies;
- no more than 3 leaders;
- highly correlated strategies cannot occupy all leader slots.

Alpaca Paper begins with a USD 25,000 simulated balance. Reports also replay USD 5,000 and USD 10,000 feasibility because the target user may operate with a smaller account in the future.

## 13. Reports

### 13.1 Research-run report

- hypotheses proposed;
- variants generated;
- counts entering and leaving every gate;
- common rejection reasons;
- promoted candidates;
- data, code, DSL, and execution-model versions.

### 13.2 Daily paper report

- strategies that signaled and why;
- symbols and intended actions;
- orders, partial fills, fills, cancellations, and rejections;
- strategy and account profit;
- drawdown and risk status;
- promotions, downgrades, pauses, and retirements;
- explicit reasons when no strategy traded.

### 13.3 Strategy detail

- plain-language rationale;
- full DSL;
- lineage and parameters;
- historical and forward results kept separate;
- paper order history;
- profit concentration and failure risks;
- similarity to other strategies.

## 14. Security and Operational Boundaries

- Paper and any future live credentials must use different types and configurations.
- The first release recognizes only the Alpaca Paper base URL.
- Startup fails if a real-money base URL is supplied.
- Secrets stay in ignored environment files and are redacted from logs and reports.
- The paper service has no mechanism to mutate research results.
- The research orchestrator has no mechanism to submit orders.
- Generated artifacts and failure evidence are append-only by default.

## 15. Testing and Acceptance

### 15.1 Data tests

- deterministic old-archive import;
- timezone, daylight-saving, holiday, and half-day behavior;
- missing, duplicate, and out-of-order detection;
- deterministic 1-minute to 5/15-minute aggregation;
- provider-overlap comparison.

### 15.2 DSL and research tests

- invalid DSL rejection;
- look-ahead rejection;
- identical signals from backtest and realtime runtimes on identical closed bars;
- deterministic run output for identical inputs;
- sealed holdout touch limits;
- perturbation and null-test behavior.

### 15.3 Trading and recovery tests

- idempotent order retries;
- partial fill, reject, cancel, and expiry handling;
- restart recovery of orders and positions;
- safe close-of-day flattening;
- entry blocking during reconciliation failure;
- hard rejection of real-money endpoints.

### 15.4 End-to-end acceptance

The first release is complete only when this flow succeeds:

`historical import → AI hypothesis → DSL variants → realistic backtest → validation → frozen bundle → paper shadow → Alpaca Paper execution → daily report → forward rank/pause`

The flow must also recover safely from at least one injected data interruption, connection interruption, and process restart.

## 16. First-Release Boundaries

Included:

- independent repository;
- traceable reuse of old minute data;
- open DSL strategy factory;
- realistic minute backtesting;
- automated validation and registration;
- Alpaca automated paper execution;
- forward leaderboards and Chinese reports;
- Windows local run and recovery instructions.

Deferred:

- real-money execution;
- order-book market making;
- paid full-market real-time feeds;
- cloud clusters and external message queues;
- mobile application;
- large web administration dashboard.

## 17. Decision Record

- 2026-07-26: selected US equities over crypto for the first low-cost route.
- 2026-07-26: selected minute-level intraday research rather than millisecond HFT.
- 2026-07-26: created the independent `G:\us-intraday-lab` repository.
- 2026-07-26: selected a hybrid of clean selective reuse and service-oriented architecture.
- 2026-07-26: selected `SPY/QQQ/IWM` for paper production and the remaining 60 symbols for robustness.
- 2026-07-26: selected fully automated paper trading, long-only, no overnight positions.
- 2026-07-26: selected a constrained DSL and AI-hypothesis plus programmatic-variation factory.
- 2026-07-26: selected hard promotion gates followed by paper-forward ranking.
- 2026-07-26: removed periodic strategy-generation schedules; research runs are user-triggered.
- 2026-07-26: retained the complete recovery state machine while documenting it in plain language.

## 18. References

- Alpaca market-data plans: <https://docs.alpaca.markets/us/docs/about-market-data-api>
- Alpaca IEX and SIP differences: <https://docs.alpaca.markets/us/docs/market-data-faq>
- Alpaca Paper behavior and limitations: <https://docs.alpaca.markets/us/v1.4.2/docs/paper-trading>
- Alpaca trade-update streaming: <https://docs.alpaca.markets/us/docs/websocket-streaming>
