# SEC original Form S-3ASR training design

## Objective and authorization

Test whether exact original issuer-filed Form S-3ASR automatic shelf
registrations create a distinct, short-lived long-only intraday return source
in the frozen 527-symbol 2021-2023 training sample. The sample is
coverage-limited and is not the full US market.

This is a versionless training-feasibility screen. It does not authorize
development- or consumed-period access, primary-document retrieval, strategy
creation, Paper activation, monitoring-pool changes, broker calls, order
routing, or shutdown actions. The outcome evaluation is frozen here before any
post-acceptance return is opened.

## Economic hypothesis and five-session life

S-3ASR is an immediately effective automatic shelf registration by a
well-known seasoned issuer. It creates financing flexibility and possible
future issuance optionality, but it is not evidence that an offering or capital
raise occurred. The test asks only whether the market's intraday response to
that issuer-direct legal action persists or reverses over the following week.

An event remains active for five observed symbol sessions, starting with the
first frozen sample session strictly after the SEC acceptance calendar date.
Five sessions are fixed because shelf optionality is less mechanically tied to
same-day issuance than S-8 registration and may be incorporated over a trading
week. This choice is made before outcomes and is not a tuning axis.

## Frozen source and causal identity

The immutable event cube has SHA-256
`399020c0abbdd554e4f4652593debcf33a2090bcc684c5d78bc1e27da92889a9`.
The frozen SEC identity snapshot has SHA-256
`44e7e15596937fe353d2148e6e775c41b83e27f9196d980bbeb44bd873d5f5b1`.
Identity is exact one-to-one numeric CIK matching only; CIK 1652044 is excluded
because it maps to GOOG and GOOGL. No security-name, parent/subsidiary, former
name, abbreviation, fuzzy, or manual alias mapping is allowed.

The frozen acceptance-coverage artifact has SHA-256
`f0efbbd0d49bbb51e219ca016f280648ef3cae447a91cbdaefef1977a5d013de`.
It contains 286 admitted issuer-accession pairs across 249 issuers after 71
otherwise valid end-censored pairs were explicitly excluded. Yearly pair counts
are 122/88/76 and yearly issuer counts are 113/82/71. All 357 requested official
filing-index pages were acquired with distinct hashes and no fetch, parse,
accession, or exact-primary-row failure.

Only exact original `S-3ASR` accessions are events. `S-3ASR/A`, S-3, EFFECT,
424B5, FWP, prospectus supplements, takedowns, offerings, withdrawals, linked
financings, and primary-document content cannot create, modify, split, or label
an event.

## Frozen repetition labels

Repetition history uses only the 286 admitted availability sessions on each
symbol's frozen sample-session index. Accessions sharing one availability
session do not count as prior events for one another.

- `first_or_renewal_252`: no earlier admitted S-3ASR availability session lies
  in the preceding 252 symbol sessions, and the complete 252-session lookback
  exists within the frozen horizon. Left-censored absence is ineligible.
- `repeat_252`: at least one strictly earlier admitted availability session
  lies in the preceding 252 symbol sessions.
- `clustered_repeat_63`: at least one strictly earlier admitted availability
  session lies in the preceding 63 symbol sessions.

Positive repeat evidence does not require a complete lookback. The current
session is excluded from every history window.

## Signal families and scores

At each decision bar, the only score input is that symbol's same-session
open-to-decision `session_return`. Event count, acceptance time, document name,
security class, filing size, and age within the five-session life are audit
fields and never score multipliers.

The five fixed families are:

1. `all_event_continuation`: all active names, rank higher return first;
2. `all_event_reversal`: all active names, rank lower return first;
3. `first_or_renewal_252_continuation`: complete-lookback first/renewal names,
   rank higher return first;
4. `repeat_252_continuation`: 252-session repeat names, rank higher return
   first; and
5. `clustered_repeat_63_reversal`: 63-session clustered repeats, rank lower
   return first.

All causally eligible active names are ranked jointly within session and
decision clock. Continuation uses within-clock percentile rank; reversal uses
one minus that rank. Ties break by symbol ascending. A symbol is ranked at most
once per clock even if multiple accessions are active. Nonfinite score inputs
are ineligible and remain explicit missingness.

## Frozen 400-cell grid and portfolio

The diagnostic evaluates exactly five families times decision bars
`(2, 5, 11, 17, 23)` times holding bars `(1, 2, 4, 6)` times top counts
`(1, 3, 5, 10)`, for 400 unique cells.

Entry is the first bar open after the decision. Exit is the open after the
selected holding count. The one-delay stress moves entry and exit one bar later
without changing holding length. Portfolios select up to K names, equal-weight
available names, remain long-only with gross exposure at most one, and exit
intraday without overnight carry. Standard round-trip cost is 9 bp, stress cost
is 18 bp, and the delayed test uses 9 bp.

A genuine zero-signal calendar session is flat. Any selected nonpositive or
missing entry/exit price invalidates that cell; it is never filled, treated as
cash, forward-filled, or replaced.

## Retention and terminal rule

Metrics use the full frozen 2021-2023 sample-session calendar. A cell is
retained only if it has at least 120 signal sessions, 9 bp annualized net return
of at least 20%, 9 bp information ratio of at least 0.8, maximum drawdown below
20%, at least two positive calendar years, positive annualized net return at 18
bp, and positive annualized net return under one-bar delay at 9 bp.

Training passes only if valid retained cells span at least two distinct signal
families. A pass emits `ACQUIRE_DEVELOPMENT_SEC_S3ASR_DATA` and only recommends
a separately reviewed immutable development-data acquisition. A failure emits
`ABANDON_SEC_S3ASR_NO_VERSION_CREATED`. Neither result creates a version or
permits development/consumed data or execution.

The immutable event container may contain later dates. The evaluator first
audits `session_date`, uses Parquet date filters before loading outcome columns,
records metadata-only rows excluded outside 2021-2023, and rejects any evaluated
row outside training. Outputs are atomic and immutable. Every input hash, all
400 cells, invalidity, missingness, and the terminal decision are retained.
