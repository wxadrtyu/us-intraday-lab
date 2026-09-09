# Alpaca SIP Full-Market Data Design

## Status and objective

Approved direction: option A, selected by the user on 2026-09-09.

The project will replace IEX-derived universe selection with an immutable Alpaca SIP data path. The old IEX datasets remain retained as evidence but must not define eligibility, liquidity, strategy ranking, or Paper admission. The resulting dataset must support production-grade, long-only, gross-at-most-one, no-overnight US equity research over a point-in-time full-market cross-section.

This phase builds and validates the data contract. It does not create a strategy, admit a candidate, construct a broker, or place/cancel orders.

## Why the current path fails

The current daily universe applies a USD 10 million median dollar-volume threshold to Alpaca IEX bars. IEX is a single venue, so its volume is not consolidated US-market volume. This systematically understates liquidity and shrinks the eligible universe. Downstream minute events, quote features, trade features, and news features are all keyed to that already-sparse event set and therefore do not repair the bias.

The current asset catalog is also a present-day snapshot. Active/inactive flags and current classifications must not be projected backward as historical facts.

## Architecture

### 1. Immutable SIP daily acquisition

- Source: Alpaca historical stock bars with `feed=sip`.
- Date range: 2018-01-01 through the last fully closed permitted research session.
- Candidate symbols: all retained Alpaca US equity asset records, including inactive records; no current `tradable` or `active` flag may exclude a historical observation.
- Historical symbol mapping: requests use an explicit monthly `asof` date. Returned symbol mappings and provider rejections are recorded.
- Storage: a new `alpaca_sip_1day_v1` namespace under the external data root. IEX files are never overwritten or promoted into the SIP namespace.
- Partitioning: calendar month and deterministic symbol batch.
- Every partition records request bounds, symbols, feed, adjustment, row count, provider rejections, content SHA-256, retrieval time, and quality results.
- Resume is hash-aware and idempotent. An existing valid immutable partition is reused; a collision or corrupt partial partition fails closed.

### 2. Point-in-time monthly universe

For each month, eligibility uses only SIP observations available through the prior XNYS session:

- 60-session trailing window with at least 57 observed sessions.
- Split-adjusted cutoff close at least USD 5.
- SIP median daily dollar volume at least USD 10 million.
- Missing cutoff data means ineligible, never cash and never an imputed return.
- Current asset status, current exchange, and current tradability are descriptive audit fields only and cannot determine historical membership.
- Every symbol-month decision is retained with its reason, including missing, insufficient history, price failure, liquidity failure, and eligible.

The universe output is a new immutable dataset and cannot replace or mutate the IEX-derived monthly universe.

### 3. Full-market decision-event acquisition

For every eligible symbol and every permitted XNYS session in its eligible month, generate fixed decision timestamps. Acquire SIP observations for the entire expected grid, not only keys present in the old IEX event cache.

The first production contract acquires the minimum data needed for causal returns and execution checks:

- Last valid SIP quote strictly before each decision timestamp, with a maximum age of 120 seconds.
- First valid SIP quote after the decision timestamp for executable entry measurement.
- The same observations at the frozen exit horizons.
- Bid, ask, sizes, timestamps, midpoint, spread, quote age, locked/crossed state, and availability.

Historical news may be joined only after the full-market event grid exists. Existing news metadata remains reusable, but existing news feature rows keyed to the sparse IEX event cache are not full-market evidence.

### 4. Coverage and survivorship audit

Research version v18010 cannot start until the data audit passes:

- All expected months and XNYS sessions are represented or explicitly missing.
- At least 95% of eligible symbol-sessions have valid decision/entry/exit observations for every frozen primary clock used by a strategy.
- Coverage is reported by month, symbol, exchange, liquidity decile, price decile, and active/inactive snapshot status.
- No segment may be silently dropped to improve the aggregate coverage ratio.
- Current-snapshot survivorship risk remains explicitly disclosed. The SIP/asof design reduces symbol-change errors but does not claim an independently licensed historical security master.
- Any material unresolved survivorship or coverage failure sets `strategy_metrics_permitted=false` and blocks new strategy versions.

## Research boundary after the audit

Only after the data contract passes may v18010 or the next unused version be preregistered. All symbols in a session and decision clock are ranked jointly. The action universe cannot be hard-coded to TQQQ, SOXL, ETFs, or a small symbol list. Portfolios may hold at most ten ordinary eligible US equities, remain long-only, keep gross exposure at or below one, and exit before the close.

Fitting uses 2022-2023 only. Development selection uses 2024 and 2025. The 2018-2020 history and consumed 2026 windows are loaded only after candidate parameters are frozen and cannot change ranking or thresholds.

All existing return, drawdown, IR, fold, start-date, neighborhood, global-evidence, native-null, and execution-parity gates remain mandatory. Passing this data audit is an additional prerequisite, not a replacement for any strategy gate.

## Failure handling and operational safety

- Credentials are read from environment variables and never written to source, logs, manifests, or reports.
- Acquisition is market-data read-only. Broker construction and all order endpoints are forbidden.
- HTTP throttling, entitlement failures, empty provider responses, and invalid schema are recorded per partition and do not become filled data.
- Long acquisitions checkpoint atomically after each verified partition.
- Raw data, caches, credentials, runtime state, and logs remain untracked under the external data root.
- Publishable protocol, audit, test, and summary artifacts may be committed; raw data may not.

## Test and acceptance plan

Before bulk acquisition:

1. Unit tests prove the downloader always requests SIP, preserves explicit `asof`, and cannot write into an IEX namespace.
2. Unit tests prove a current inactive/tradable flag cannot remove historical rows.
3. Unit tests prove missing cutoff bars and insufficient histories fail closed.
4. Unit tests prove immutable resume accepts identical hashes and rejects collisions or corrupt partial files.
5. A read-only entitlement test confirms historical SIP daily and quote access without exposing credentials.

Before research:

1. Validate every manifest and content hash.
2. Publish eligible counts and coverage distributions by month and segment.
3. Compare IEX and SIP volumes to demonstrate that the universe no longer uses venue-only liquidity.
4. Verify 2026 and blind-period files were not used for fit or ranking.
5. Set `strategy_metrics_permitted=true` only when every data gate passes.

## Out of scope

- Paper trading or live trading.
- Re-enabling v11098, v1254, or any fixed small-universe strategy.
- Cross-provider minute splicing.
- Filling absent prices, quotes, or sessions.
- Claiming complete historical survivorship coverage without an independently verified historical security master.
