# Polygon Point-in-Time Listing Lifecycle Alpha Design

## Status

Frozen for implementation planning on 2026-09-16. This document authorizes a
research-only implementation plan. It does not authorize strategy admission,
Paper activation, broker access, order submission, cancellation, or any change
to an existing observation pool.

## Objective and hypothesis

Evaluate whether point-in-time listing lifecycle state changes the conditional
payoff of causal intraday price-volume signals across the full eligible US
equity universe.

The economic hypothesis is that recently visible listings, maturing listings,
seasoned listings, and genuinely reactivated tickers can differ in liquidity
formation, attention, inventory absorption, and price discovery. Lifecycle is
therefore an interaction variable, not a standalone claim that young or old
stocks must rise or fall. Every tested signal combines a lifecycle state known
before the session with intraday information known at the decision clock.

The campaign reserves `v18010` through `v18109`: five preregistered signal
families, five decision clocks, and four holding periods, for exactly 100 frozen
research units.

## Non-goals

- Do not use Polygon lifecycle data to rewrite the Alpaca monthly universe.
- Do not infer daily listing or delisting dates from monthly snapshots.
- Do not reconstruct corporate-action histories or stitch old and new tickers.
- Do not use `delisted_utc`, `last_updated_utc`, future `active` values, names,
  CIK, composite FIGI, or share-class FIGI as alpha inputs.
- Do not tune on 2018-2020 historical stress or the consumed 2026 Q1 period.
- Do not create a small-symbol, ETF-only, or broad-market-context substitute
  for a full-market strategy.
- Do not add execution, Paper, broker, submit, or cancel paths.

## Immutable inputs and lineage

The implementation must consume the already validated artifacts through their
manifests and audit reports, never through an operator assertion or bare file
existence check:

- Polygon US-stock monthly reference snapshots, 99 month ends from 2018-01
  through 2026-03, including both active and inactive query partitions;
- the independent Polygon historical-master audit that validates all pages,
  snapshot hashes, activity partitions, missingness, and provider lineage;
- the existing monthly point-in-time Alpaca eligibility decisions;
- the audited Alpaca SIP five-minute dataset; and
- the hash-addressed, read-only causal research catalog whose membership and
  information-cutoff contract is `causal-membership-cutoff-v1`.

Every campaign manifest records the exact source paths, source content hashes,
audit hashes, universe hash, catalog hash, code revision, version allocation,
date roles, cost assumptions, and null-test seeds. Any mismatch blocks reuse or
resume. Polygon and Alpaca fields remain separate sources; no provider splicing
is allowed.

## Point-in-time lifecycle contract

### Monthly cutoff

For each trading month `M`, use exactly the latest validated Polygon snapshot
whose `asof` date is strictly earlier than the first eligible trading session
of `M`. No snapshot dated on or after that session may contribute to that
month's features.

The lifecycle history available at that cutoff consists only of the ordered
validated snapshots at or before the selected cutoff. The implementation must
derive lifecycle state deterministically from those snapshots and record the
cutoff snapshot date and hash on every monthly partition.

### Symbol identity

Join the monthly eligible symbol to the Polygon snapshot by exact ticker after
a separately audited ASCII-uppercase normalization. The normalization audit
must prove that it creates no collisions in either source for every month.

No FIGI-, CIK-, name-, or heuristic-based retroactive stitching is permitted.
A ticker change therefore starts a separate observable ticker history unless a
future, separately approved point-in-time identity contract proves otherwise.

### Derived fields

Only the following lifecycle fields are permitted:

- `first_observed_active_month`: earliest available snapshot at or before the
  cutoff in which this exact ticker has `active=true`;
- `active_tenure_months`: whole elapsed calendar months from
  `first_observed_active_month` to the selected cutoff month, with value zero
  in the first observed active month;
- `left_censored`: true when the ticker is already active in the first Polygon
  snapshot in January 2018, so its actual listing age is unknown;
- `reactivated_this_month`: true only when the ticker changes from an observed
  `active=false` state in the immediately preceding available snapshot to
  `active=true` in the selected cutoff snapshot; and
- `lifecycle_bucket`: one of `new_0_3`, `young_4_12`, `maturing_13_36`,
  `seasoned_37_plus`, or `left_censored`.

`left_censored` is its own known state and must never be treated as a seasoned
age estimate. A missing prior observation is not an inactive observation. A
known false predicate may become a zero indicator; missing or ambiguous source
data may not become zero, neutral, cash, or an inferred lifecycle state.

## Mandatory full-universe coverage gate

Coverage is audited before any strategy return is computed or any strategy
result artifact is published. For every research month:

1. Every symbol in every monthly eligible set must map to exactly one record in
   the selected prior Polygon snapshot after audited normalization.
2. The snapshot cutoff must be strictly causal and its full preceding history
   must pass the historical-master audit.
3. There must be zero case-fold collisions, duplicate matches, unmatched
   eligible symbols, ambiguous histories, missing lifecycle states, or
   untraceable hashes.
4. Every session and decision clock must jointly rank all eligible symbols that
   have causal SIP bars at that clock under the existing bar-availability
   contract. Symbols missing causal bars remain explicit missing-data evidence;
   they are not silently excluded or assigned a neutral score.

The required monthly lifecycle mapping coverage is 100%. Any failure stops the
campaign before version evaluation. The audit publishes exact exception rows
and the campaign status `BLOCKED_LIFECYCLE_COVERAGE`; it must not publish a
partial or deceptively full-market result.

## Frozen signal families

All raw intraday terms are computed cross-sectionally from causal bars available
at the decision clock and then interacted with the frozen lifecycle states.
Winsorization, standardization, eligibility, ranking, portfolio construction,
and tie breaking reuse the existing full-universe evaluator without adding a
new execution model.

1. `young_listing_continuation`: within-session return from the open to the
   decision clock, signed for continuation and interacted with
   `new_0_3`/`young_4_12` membership.
2. `young_listing_reversal`: the negative of the same within-session return,
   interacted with `new_0_3`/`young_4_12` membership.
3. `age_conditioned_volume_absorption`: price change divided by causal dollar
   volume, cross-sectionally signed so unusually high volume for limited price
   movement ranks as stronger absorption, with separate lifecycle-bucket
   interactions.
4. `age_conditioned_vwap_dislocation`: decision-price displacement from causal
   session VWAP, signed for mean reversion, with separate lifecycle-bucket
   interactions.
5. `reactivation_flow`: causal return and relative-dollar-volume interaction
   gated by `reactivated_this_month`; non-reactivated is a known false predicate
   rather than missing data.

The implementation plan must specify the exact formula, denominator floor,
cross-sectional transform, deterministic tie rule, and behavior when the raw
term is undefined before code is written. It may not add alternative signs,
buckets, thresholds, or feature combinations after observing results.

## Frozen 100-unit grid

- Families: the five listed above.
- Decision clocks: minutes `2`, `5`, `11`, `17`, and `23` after the regular
  session open.
- Holding periods: `1`, `2`, `4`, and `6` five-minute bars.
- Allocation order: family order above, then ascending decision clock, then
  ascending holding period.
- Version range: sequentially `v18010` through `v18109`, with no skipped,
  recycled, or dynamically added versions.

Positions are intraday only and close at the frozen holding horizon or earlier
at the existing session boundary. Gross exposure, top-k selection, liquidity
filters, non-overlap behavior, transaction-cost accounting, and delay handling
must reuse the exact current full-universe evaluator. If that evaluator cannot
represent a family without changing its execution semantics, the family is
blocked rather than silently implemented in a parallel framework.

## Date roles and anti-selection boundaries

- Fit: 2022-01-01 through 2023-12-31.
- Development selection: 2024-01-01 through 2025-12-31.
- Historical stress: the first eligible session after the January 2018
  snapshot through 2020-12-31, evaluated only for a candidate frozen without
  access to those returns. January 2018 has no strictly prior Polygon snapshot
  and is retained as structural missingness rather than backfilled.
- Consumed diagnostic: 2026-01-01 through 2026-03-31, reported only after the
  candidate and all decisions are frozen; it cannot rank, tune, revive, or
  qualify a candidate.
- 2021 is excluded from ranking and reserved as an unconsumed bridge/gap unless
  a later approved protocol assigns it before results are inspected.

The campaign may use fit data to estimate only preregistered transforms. Family,
clock, horizon, ranking, and candidate selection use development evidence under
the frozen multiplicity rules. Historical stress and consumed diagnostics are
append-only observations, never inputs to search.

## Costs, robustness, and hard gates

Every unit reports the standard 9 bp round-trip scenario, 18 bp round-trip
stress, and the existing five-minute delayed-entry scenario using identical
signals and membership. Candidate status is fail-closed and requires all
current production gates, including:

- primary development annualized return greater than 40%, maximum drawdown
  below 20%, information ratio at least 1.0, and the current `z >= 3.0` rule;
- at least four of five positive development folds and every preregistered
  start-date observation positive;
- at least 70% passing share in the frozen local neighborhood;
- historical 2018-2020 annualized return at least 15% in every required
  scenario and maximum drawdown below 20%;
- cumulative/global Bonferroni-adjusted significance at or below 0.05 across
  the applicable strategy ledger; and
- consumed 2026 Q1 total return at least 5%, diagnostic only and incapable of
  changing selection.

The implementation must read these thresholds from the current authoritative
gate policy where one exists and record the policy hash. If code and this design
disagree, stop and produce a gate-contract discrepancy instead of choosing the
more favorable threshold.

## Native nulls and multiplicity

Only a candidate that passes every pre-null gate proceeds to both native null
methods:

- `session_signal_permutation_maxT`, 500 repetitions; and
- `safe_circular_shift_maxT`, 500 repetitions.

Nulls operate on the candidate's exact native full-market signal factory,
lifecycle membership, decision clock, holding period, portfolio construction,
costs, and eligibility. Surrogate returns, reduced universes, or a generic
post-hoc score permutation are not substitutes. Each method records its seed,
actual repetitions, complete max-statistic distribution hash, failures, and
familywise-adjusted result. A timeout or incomplete null is a failed gate, not
a pass.

The 100 units enter the cumulative research ledger whether they pass or fail.
No attractive return or IR can override multiplicity, robustness, missingness,
historical, or native-null failure.

## Artifacts and completion criteria

The implementation must produce immutable, hash-addressed artifacts for:

- the lifecycle mapping and monthly cutoff lineage;
- the normalization/collision and 100% coverage audit;
- the frozen 100-unit registry;
- per-unit metrics and fold/start/scenario evidence;
- the selection decision and local-neighborhood definition;
- historical and consumed-period supplements;
- both native-null outputs for every pre-null candidate; and
- a final machine-readable summary with completed versions, status, source
  hashes, gate outcomes, and explicit rejection reasons.

The campaign is complete only when the final summary status is `COMPLETE`, all
100 reserved versions are accounted for, every pre-null candidate has two
complete 500-repetition native-null results, and all artifacts validate against
their manifests. `COMPLETE` does not mean admitted.

The only possible research conclusions are:

- `NO_CANDIDATE`: all evidence retained; no strategy admission;
- `RESEARCH_QUALIFIED_AWAITING_HUMAN_REVIEW`: every gate passed, but no Paper or
  monitoring action occurs; or
- a fail-closed blocked/fault status with exact preserved evidence.

Any admission, observation-pool addition, Paper allocation, or runner activation
requires a separate exact execution-parity review and explicit human approval.
