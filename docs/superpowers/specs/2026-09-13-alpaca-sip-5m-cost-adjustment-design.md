# Alpaca SIP Five-Minute Full-Market Cost Adjustment

## Status and scope

Approved in conversation on 2026-09-13. This document supplements, rather than
rewrites, `2026-09-09-alpaca-sip-full-market-data-design.md`.

The full-market research substrate changes from historical SIP quote updates to
Alpaca consolidated SIP five-minute bars. Historical quotes remain mandatory,
but only for exact execution validation of a fully frozen candidate after all
research, stress, multiplicity, and native-null gates pass.

This phase remains market-data read-only. It cannot construct a broker, modify
the Paper pool, submit or cancel an order, or admit a strategy.

## Evidence for the adjustment

A read-only entitlement pilot requested two minutes of SIP quotes for 30 symbols
sampled across December 2025 liquidity ranks. Alpaca returned 60,709 quote
updates: a median of 309.5 and a 90th percentile of 3,306.5 updates per symbol.
Applying the frozen 21 unique execution timestamps per session to the 2,947
eligible symbols in that month implies an order of roughly 30 billion quote
updates per year and roughly 250 billion over the intended history. This is a
capacity estimate, not an exact row forecast, but it is sufficient to reject
full-market quote-tick acquisition as the low-cost base dataset.

The rejected quote-grid protocol and its pilot evidence remain retained. They
must not be relabeled as a completed production dataset.

## Data architecture

### Immutable SIP five-minute acquisition

- Provider: Alpaca historical stock bars.
- Feed: exactly `sip`; IEX rows cannot enter the dataset.
- Timeframe: exactly five minutes.
- Adjustment: split-adjusted.
- Range: 2018-01-01 through 2026-03-31 for the frozen research corpus.
- Candidate request set: all 15,399 symbols in the frozen Alpaca asset snapshot,
  including inactive records; current active or tradable flags cannot remove a
  historical request.
- Historical mapping: every production request carries its declared end as an
  explicit `asof` value. That is calendar month-end for complete months and the
  requested end for a deliberately bounded pilot or final partial month.
- Namespace: `data/staging/alpaca_sip_5min_v1` under the external data root.
- Partition key: calendar month and deterministic symbol batch.
- Resume identity: provider, feed, timeframe, adjustment, start, end, asof,
  ordered symbols, and batch size all contribute to the request hash.
- Every Parquet partition has a paired JSON manifest containing the exact
  request, row count, content SHA-256, retrieval timestamp, provider rejections,
  and quality findings.
- Alpaca's endpoint includes extended-hours bars. The normalization boundary
  deterministically retains only timestamps within each XNYS session's actual
  open and close (including half days), and every manifest records both the
  provider row count and the excluded extended-hours row count. This is an
  explicit source transformation, not silent data repair.
- Existing complete partitions are reused only after request-identity and
  content validation. Partial or conflicting partitions fail closed.

Raw bars, manifests, logs, and checkpoints remain outside Git. Only code,
protocols, tests, and bounded audit reports may be committed.

### Causal research cube

Monthly membership comes only from
`us-market-monthly-universe-sip-v2-3dc89bc9ab09e193372b2071`. For every XNYS
session and frozen decision bar, all point-in-time eligible symbols form one
joint cross-section. A strategy may later select at most ten ordinary equities,
but the ranking input cannot be a hard-coded ETF or ticker subset.

The initial frozen research clocks remain:

- Decision bars: `2, 5, 11, 17, 23` on the 78-bar regular-session grid.
- Holding horizons: `1, 2, 4, 6` five-minute bars.
- Signal information cutoff: the end of the completed decision bar.
- Standard entry: the open of the next observable five-minute bar.
- Delay stress: the following bar, five minutes after standard entry.
- Exit: the open at the frozen holding horizon.

No bar whose interval starts at or after the information cutoff may become a
signal feature. Missing entry or exit bars invalidate that symbol-event; they
cannot become zero return, forward-filled price, or cash performance.

### Research and diagnostic boundaries

- Fit and threshold estimation: 2022-2023 only.
- Development selection: 2024, 2025, and their combined period.
- Historical stress after freezing: 2018-2020 only.
- Consumed diagnostics after freezing: 2026 Q1 and all available 2026 only.
- 2021 may support causal feature construction and information-contract
  diagnostics, but cannot alter the declared fit/development split.

These roles are embedded in the frozen dataset protocol and checked when a
research cube is opened. A downstream evaluator must fail if a consumed or
historical-stress row enters fitting or ranking.

## Coverage and provenance gates

Before version `v18010` or any later strategy is created, an audit must prove:

1. Every requested month and deterministic symbol batch has a paired,
   hash-valid partition with the expected request identity.
2. Every expected XNYS session is represented or explicitly recorded missing.
3. At least 95% of eligible symbol-sessions contain every five-minute bar needed
   by all frozen primary decision, standard-entry, delayed-entry, and exit
   clocks.
4. Coverage is reported by month, symbol, current exchange, liquidity decile,
   price decile, and current-snapshot active status. No segment can be omitted
   to improve the aggregate ratio.
5. After the declared regular-session normalization, duplicate
   symbol-timestamps, off-grid or residual out-of-session bars, invalid OHLC
   relationships, nonpositive prices, and negative sizes fail the affected
   partition; they are never silently repaired.
6. SIP and IEX can be compared for source-bias diagnostics but their rows are
   never spliced.
7. The independently verified historical security master gate still passes.
   SIP/asof and inactive-symbol requests reduce bias but do not replace this
   evidence.

Until all seven conditions pass, `strategy_metrics_permitted=false`.

## Candidate-only quote execution validation

Historical SIP quote updates are fetched only after a candidate is completely
frozen and has passed every pre-execution gate, including both 500-repetition
native maxT tests. Acquisition keys are the candidate's exact prospective
decision, standard entry, delayed entry, and exit timestamps for its actual
selected symbols, not the full research cross-section.

For each key the validator requires the last valid quote strictly before the
decision cutoff or the first valid quote at or after an execution timestamp,
bounded by 120 seconds. Bid, ask, sizes, quote timestamp, quote age, spread,
locked/crossed state, and missingness are retained. Missing, stale, locked, or
crossed execution evidence rejects the affected trade or candidate under the
predeclared parity policy; it cannot be replaced with IEX or a fitted spread.

Quote results are execution validation only. They cannot change factors,
thresholds, ranking, holding horizons, or candidate choice.

## Failure handling and operational safety

- Credentials come only from the active environment and never enter files or
  logs.
- Entitlement, throttling, empty response, schema, and quality failures are
  recorded at the exact request identity and fail closed.
- Acquisition checkpoints atomically after each verified partition.
- Disk-space and estimated completion-time checks run before each bulk phase;
  an unsafe estimate stops acquisition before filling the volume.
- The Paper pool remains empty. Existing fixed-universe strategies remain
  disabled and cannot be used as a fallback.

## Acceptance tests

Before bulk acquisition, automated tests must prove the downloader always uses
SIP five-minute bars, preserves `asof`, produces deterministic month/batch
identities, validates immutable resume, and has no trading-client imports.

Before research, a production audit must validate every manifest and hash,
publish the exact expected/observed grid and segmented coverage, confirm source
is SIP only, verify the historical-master gate, and demonstrate that date-role
separation is enforced. Passing framework tests alone does not permit strategy
metrics.
