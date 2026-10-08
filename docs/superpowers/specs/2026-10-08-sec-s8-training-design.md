# SEC original Form S-8 training design

## Objective and authorization

Test whether issuer-filed original Form S-8 registrations create a distinct,
short-lived long-only intraday return source in the frozen 527-symbol
2021-2023 training sample. This sample is coverage-limited and is not the full
US market.

This is a versionless training-feasibility screen. It does not authorize
development- or consumed-period access, strategy creation, Paper activation,
monitoring-pool changes, broker calls, order routing, or shutdown actions. The
design freezes the outcome evaluation before any post-acceptance return is
opened.

## Alternatives and approved choice

Three alternatives were presented before outcome access:

1. a three-session event life with five timing and repetition families;
2. the same families with a five-session event life;
3. retrieval of primary-document bodies followed by legal-subtype
   classification and a new coverage/design review.

The user selected option 1. Three sessions are used because the hypothesis is a
short-lived market reaction to an automatically effective registration, while
limiting overlap between repeated filings. Primary-document bodies remain
unopened, and no plan name, share count, security class, executive, tranche, or
document section becomes a feature or pseudo-event.

## Frozen inputs and identity

The immutable event cube has SHA-256
`399020c0abbdd554e4f4652593debcf33a2090bcc684c5d78bc1e27da92889a9`.
Only its 2021-2023 `symbol` and `session_date` columns were opened during the
coverage stage. The frozen SEC identity snapshot has SHA-256
`44e7e15596937fe353d2148e6e775c41b83e27f9196d980bbeb44bd873d5f5b1`.
Issuer identity is exact one-to-one numeric CIK matching only. CIK 1652044 is
excluded because it maps to both GOOG and GOOGL. No security-name inference,
parent/subsidiary link, former name, abbreviation, fuzzy match, or manual alias
is allowed.

The source census is the 12 official EDGAR quarterly master indexes for
2021-2023, filtered by exact form equality `S-8`. It contains 7,909 original
S-8 accessions and separately excludes 5,375 `S-8 POS` records and every other
form. The one-to-one sample boundary yields 620 issuer-accession candidates.
All 620 official filing-index pages were fetched sequentially, have distinct
SHA-256 hashes, and contain a consistent accession, accepted timestamp, and
exactly one `S-8` primary-document row. The acceptance-coverage artifact has
SHA-256
`62943eb65d564e07960efcd206563adf1baebd5715d0c2db30a56cbe15be2ca8`.

The frozen admissible set excludes 138 end-censored pairs without a later
sample session and retains 482 issuer-document pairs across 258 issuers. The
yearly pair counts are 220/150/112 and yearly issuer counts are 175/130/93.
Sixty-two issuers have at least three events, and maximum issuer concentration
is 8/482. These counts are coverage evidence, not strategy results.

## Causal availability and three-session state

One event is one exact original S-8 accession. Its causal availability session
is the already-frozen first sample session strictly after the SEC acceptance
calendar date. Same-day use is forbidden even for pre-market acceptance. An
admitted event is active on that availability session and the next two frozen
sample sessions for the symbol, then expires. The state is not backfilled into
an earlier session and does not extend beyond three observed symbol sessions.

Multiple qualifying accessions may be active for one symbol, but the symbol is
ranked at most once at a decision clock. Active accessions and their acceptance
timestamps remain attached for audit. A later filing creates a new event; it
does not revise an earlier state. `S-8 POS`, amendments on other forms,
withdrawals, substitute filings, 8-K, 10-K, proxy, press, and primary-document
content cannot create or modify a state.

## Frozen repetition labels

Repetition labels are fixed before return access. The 620 metadata-valid exact-
S-8 rows are the audit inventory, but only the 482 rows with a frozen mapped
availability session can enter repetition history. History is measured on the
frozen sample-session index by availability session. Accessions sharing an
availability session do not count as prior events for one another.

- `first_or_renewal_252`: no earlier exact-S-8 availability session for the
  issuer lies in the preceding 252 sample sessions. This label is usable only
  when a complete 252-session lookback exists inside the frozen source and
  sample horizon; left-censored observations are ineligible rather than
  assumed to be first.
- `repeat_252`: at least one earlier exact-S-8 availability session for the
  issuer lies in the preceding 252 sample sessions.
- `clustered_repeat_63`: at least one earlier exact-S-8 availability session
  for the issuer lies in the preceding 63 sample sessions.

The windows exclude the current availability session and include exactly the
prior 252 or 63 sample sessions. Positive repeat evidence does not require an
otherwise complete lookback; absence-based `first_or_renewal_252` does.

## Frozen signal families and scores

At each decision bar, the causal price input is the symbol's open-to-decision
`session_return` for that same session and bar. Eligibility is binary; event
counts, acceptance time, filing size, document name, and recency within the
three-session life are audit fields, not score multipliers or tuning axes.

The five families are:

1. `all_event_continuation`: any active event; rank higher open-to-decision
   return first.
2. `all_event_reversal`: any active event; rank lower open-to-decision return
   first.
3. `first_or_renewal_252_continuation`: any active event carrying the complete-
   lookback `first_or_renewal_252` label; rank higher return first.
4. `repeat_252_continuation`: any active event carrying `repeat_252`; rank
   higher return first.
5. `clustered_repeat_63_reversal`: any active event carrying
   `clustered_repeat_63`; rank lower return first.

Within every session and decision bar, all causally eligible active symbols in
the frozen sample are ranked jointly. Ties break by symbol ascending. A
continuation score is the within-clock percentile rank of `session_return`; a
reversal score is one minus that percentile rank. Nonfinite score inputs are
ineligible and remain explicit missingness.

## Portfolio construction and frozen 400-cell grid

The diagnostic evaluates exactly:

- five families;
- decision bars `(2, 5, 11, 17, 23)`;
- holding bars `(1, 2, 4, 6)`;
- top counts `(1, 3, 5, 10)`.

This is `5 x 5 x 4 x 4 = 400` unique cells. Standard entry is the first bar
open after the decision and exit is the open after the selected holding count.
The only delay test moves both entry and exit one bar later, preserving holding
length. Portfolios take up to the requested top count, equal-weight the
available names, are long-only with gross exposure at most one, and are flat at
the frozen exit. No overnight carry or short exposure is allowed.

Standard round-trip cost is 9 bp per active portfolio session. Stress cost is
18 bp. The delayed-entry test uses 9 bp. A genuine zero-signal calendar session
is an observed flat session. If any selected name has a missing or nonpositive
entry or exit price, that cell fails closed and produces no retention decision;
the missing value is never filled with zero, treated as cash, forward-filled,
or replaced by another symbol.

## Training metrics, retention gates, and terminal rule

Metrics use the full frozen 2021-2023 sample-session calendar so inactivity is
represented honestly. Annualized return uses 252 sessions, information ratio
uses the full-calendar daily series, and maximum drawdown is computed from the
same net-return path.

A cell is retained only if all of the following hold:

- at least 120 observed signal sessions;
- 9 bp annualized net return at least 20%;
- 9 bp information ratio at least 0.8;
- maximum drawdown below 20%;
- at least two positive calendar years;
- positive annualized net return at 18 bp;
- positive annualized net return under the one-bar delay at 9 bp.

Training passes only if retained cells span at least two distinct signal
families. A pass emits `ACQUIRE_DEVELOPMENT_SEC_S8_DATA` and only recommends a
separately reviewed development-data acquisition. A failure emits
`ABANDON_SEC_S8_NO_VERSION_CREATED`. Neither outcome creates a strategy version
or permits development/consumed data access.

## Failure handling and verification

Source-hash, accession, CIK, timestamp, exact-form, duplicate, training-boundary,
lookback, event-lifetime, grid-cardinality, or price-validity failures are
preserved and fail closed. Interrupted outputs are written atomically and never
replace a completed artifact. The evaluator must reject any date outside
2021-2023 and any input hash not explicitly frozen in the implementation plan.

Tests must cover immutable input hashes, exact 400-cell identity, next-session
availability, three-session expiry, same-session multi-accession handling,
252-session left censoring, 252- and 63-session repetition labels, opposite
continuation/reversal ordering, deterministic tie-breaking, up-to-K weighting,
9/18 bp costs, one-bar delay, full-calendar metrics, every retention predicate,
terminal decisions, and absence of execution or pool mutation paths.

No primary-document body, post-acceptance return, development period, consumed
period, broker, submit/cancel function, Paper state, monitoring pool, order
route, or shutdown action is opened or changed by this design stage.
