# Point-in-Time News Training Feasibility Design

## Status

Frozen before diagnostic outcomes on 2026-09-16. This is a training-only data
acquisition decision aid. It allocates no strategy version, cannot qualify a
candidate, and cannot authorize Paper, broker, or order behavior.

## Decision being tested

Determine whether the already acquired 2021-2023 Alpaca News metadata contains
enough causal, cost-adjusted cross-sectional information to justify the roughly
15,000 additional provider calls needed for 2024-2025 development acquisition.

The diagnostic must not open development, consumed, or 2026-04+ news. A positive
training result permits only a separate development-acquisition plan; a negative
result abandons this news contract without creating `v18010` or any successor.

## Immutable inputs

- `us_market_news_training_features_v1.parquet`, exactly 388,745 event keys,
  SHA-256 `d5b83060c7bb5e8cc4d97192e1df2518e3313b269b3591d5715f5fc88180b209`;
- `v14309_v14408_events.parquet`, whose frozen protocol records SHA-256
  `399020c0abbdd554e4f4652593debcf33a2090bcc684c5d78bc1e27da92889a9`;
- `alpaca-news-event-metadata-v1`, causal availability `updated_at` strictly
  before decision time, frozen lexical hash
  `3bdd74da39dbe29163ed4da1aeca2aff6c4215a202a47a8076dc30cc8694cda6`.

The implementation verifies hashes, one-to-one event keys, identical symbol,
session, and decision-bar identity after the merge, and dates entirely within
2021-01-01 through 2023-12-31. Explicit no-news rows remain zero/false and are
not dropped. No raw text is loaded.

## Scope limitation

The frozen feature cache covers the earlier event grid, not every member of the
new SIP full-market universe. Results are therefore feasibility evidence only,
never a full-market strategy result. If retained, later development work must
rebuild news features for every eligible session/decision key and pass a fresh
100% coverage audit before any versioned strategy evaluation.

## Frozen signal families

Within each `(session_date, bar_idx)` cross-section, rank each finite component
with deterministic average percentile ranks. Known zero news counts are valid;
missing rows are invalid and block the diagnostic.

1. `recent_attention_continuation`:
   `rank(decayed_article_count_2h) + rank(session_return)`.
2. `negative_news_reversal`:
   `rank(negative_count_1d - positive_count_1d) - rank(session_return)`.
3. `positive_news_continuation`:
   `rank(positive_count_1d - negative_count_1d) + rank(session_return)`.
4. `earnings_guidance_continuation`:
   `rank(earnings_count_1d + guidance_count_1d) + rank(session_return)`.
5. `adverse_event_reversal`:
   `rank(financing_count_5d + litigation_count_5d + regulatory_count_5d) - rank(session_return)`.

Rank descending by score and then ascending exact symbol for deterministic ties.

## Frozen grid and returns

- Decision bars: `2`, `5`, `11`, `17`, `23`.
- Holding bars: `1`, `2`, `4`, `6`.
- Top counts: `1`, `3`, `5`, `10`.
- Families: five above.
- Total cells: `5 * 5 * 4 * 4 = 400`.
- Entry: next five-minute open (`p1_open`).
- Standard exits: `p2_open`, `p3_open`, `p5_open`, `p7_open`.
- Delay entry: `p2_open`; delay exits: `p3_open`, `p5_open`, `p7_open`,
  `p8_open`.
- Costs: 9 bp standard, 18 bp stress, and delayed entry with 9 bp.
- Daily return: equal-weight mean of selected event returns; non-event sessions
  are explicit zero only for this feasibility diagnostic and must not later be
  represented as economic cash performance in a full-market campaign.

## Retention floor

A cell is retained only when all are true:

- at least 120 signal sessions;
- standard 9 bp annualized return at least 20%;
- standard 9 bp information ratio at least 0.80;
- standard 9 bp maximum drawdown below 20%;
- at least two of the three calendar years have positive standard returns;
- 18 bp annualized return is positive; and
- delayed-entry 9 bp annualized return is positive.

The news contract is worth development acquisition only if at least one cell is
retained and the retained set spans at least two signal families. This breadth
rule prevents a single isolated training optimum from triggering a large data
download.

## Outputs and boundary

Publish a complete JSON summary and Parquet cell table atomically. Record input
hashes, 400 completed cells, training-only date audit, retained count/families,
best cell, runtime, and `development_or_consumed_loaded=false`.

Possible decisions are only:

- `PROCEED_TO_SEPARATE_DEVELOPMENT_ACQUISITION_PLAN`; or
- `ABANDON_NEWS_CONTRACT_NO_VERSION_CREATED`.

Neither decision admits a strategy. Paper activation remains false and order
routing remains forbidden.
