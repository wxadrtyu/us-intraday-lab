# Point-in-Time News Event Contract Design

Design decision: selected under the user's standing instruction to continue
research autonomously, prefer a genuinely distinct return source, and never
lower the frozen admission gates.

## Purpose

Add a causal, low-cost Alpaca News metadata lane to the existing intraday
research factory. The lane tests whether recent public-news flow improves
cross-sectional long-only intraday selection without using historical text
labels from an LLM and without changing the active v11098 Paper runner.

This is a research-data contract, not a strategy admission. A candidate may
advance only through the existing development, stress, multiplicity,
native-null, consumed-period, and execution-parity gates.

## Alternatives

1. **Fixed UTC-day all-market pagination (chosen).** Query the Alpaca historical
   News endpoint one UTC day at a time, follow every `next_page_token`, dedupe by
   news ID, and build local event features. This is bounded, auditable, and does
   not bias acquisition toward today's known symbol universe.
2. **Per-symbol or symbol-batch acquisition (rejected).** It creates many more
   requests, complicates deduplication of multi-symbol articles, and can embed
   universe-selection bias.
3. **Hourly all-market slices (rejected as default).** It reduces the impact of
   a failed request but multiplies calls and boundary duplicates. Daily raw
   partitions plus resumable page checkpoints provide the same recovery
   property more cheaply.

## Causal Availability Boundary

The endpoint's time filter is observed to follow `updated_at`, and returned
headline or summary text may reflect a revision made after `created_at`.
Therefore the only permissible causal availability time is:

`available_at = updated_at`

The final returned headline and summary may be used only when
`available_at < decision_cutoff`. `created_at` is retained solely for audit.
No feature, count, or symbol association may be backdated to `created_at`.

## Raw Data Contract

Acquisition uses direct HTTPS against `https://data.alpaca.markets/v1beta1/news`
with ascending order, a half-open UTC-day interval, a fixed page size, and
explicit `next_page_token` traversal.

Persist only:

- news ID;
- `created_at` and `updated_at`;
- source;
- symbols;
- headline and summary only long enough to derive deterministic local lexical
  features, unless the frozen protocol explicitly requires encrypted raw-text
  audit storage outside Git;
- request interval, page token hash, response hash, row count, and acquisition
  timestamp.

Never persist or inspect `content`, images, URL, or author. Never log API keys,
secret keys, raw response headers, or full page tokens. Raw partitions, caches,
credentials, and acquisition state remain untracked.

Each completed UTC-day partition is immutable and content-addressed. A day is
accepted only when pagination terminates normally, news IDs are unique after
deterministic deduplication, timestamps fall within the queried `updated_at`
interval, and a manifest records every page hash. Partial days fail closed and
are safe to resume from the last verified page.

## Feature Contract

For every existing event key, emit a row even when no eligible news exists.
The full cache must contain exactly the frozen 799,799 event keys in their
original order and must not drop missing/no-news observations.

Features use only articles whose `available_at` is strictly earlier than the
decision cutoff. Fixed lookbacks are 30 minutes, 2 hours, 1 day, and 5 days.
The initial feature set is deliberately deterministic and compact:

- eligible article count and exponentially decayed count;
- unique source count and source concentration;
- recency of the latest eligible article;
- multi-symbol breadth and symbol-specific article share;
- positive, negative, uncertainty, earnings, guidance, financing, litigation,
  regulatory, merger, and product-event token counts from a frozen lexicon;
- headline/summary disagreement and repeated-story intensity based on stable
  normalized token hashes.

There is no LLM labeling, embedding model, vendor sentiment score, online model
call, or retrospective manual relabeling. Tokenization, lexicons, negation
handling, decay constants, lookbacks, and normalization must be frozen before
acquiring development data.

## Chronological Isolation

- 2021-2023: training and training-only feasibility diagnostics.
- 2024-2025: development evaluation only after protocol and code hashes freeze.
- 2026Q1: consumed diagnostic only after the candidate is frozen.
- 2026-04 onward: forbidden.

No date outside 2021-2023 may influence feature choice, lexicon content,
thresholds, model choice, parameter ranking, or acquisition repair decisions.
Provider gaps remain explicit; news data is never spliced with another vendor.

## Research and Execution Boundaries

The first probe is limited to training dates and validates pagination,
deduplication, causal cutoff behavior, explicit zero rows, storage exclusion,
coverage, and expected request cost. Bulk acquisition requires that probe to
pass and a protocol commit to exist first.

Research remains long-only, gross exposure no greater than 1, and flat by the
close. The news lane cannot construct a broker, submit or cancel orders, modify
the Paper pool, or change v11098 parameters. A future admitted candidate must
have a separate production feature evaluator and exact signal/exposure parity
evidence before Paper activation.

## Failure Handling

- Missing credentials fail closed without recovering secrets from history.
- HTTP rate limits or disconnects retain verified pages and retry with bounded
  backoff; they never turn a partial day into an accepted day.
- Reused news IDs with different canonical metadata create an incident rather
  than silently overwriting evidence.
- A record with absent or invalid `updated_at` is excluded with a counted
  reason and cannot contribute to a zero/no-news claim.
- Any persisted forbidden field, cutoff leakage, duplicate event key, missing
  event key, or access to 2026-04+ invalidates the artifact.

## Verification

Tests must prove direct pagination, token handling, deterministic deduplication,
revision-safe `updated_at` cutoffs, forbidden-field removal, stable lexical
features, exact zero/no-news rows, immutable manifests, partial-day recovery,
training/development/consumed boundaries, and absence of broker imports or
state mutation. The training probe report must state request/page counts,
unique news IDs, symbol links, coverage, rejected-row reasons, cache hashes,
runtime, and estimated full-acquisition calls before bulk download begins.
