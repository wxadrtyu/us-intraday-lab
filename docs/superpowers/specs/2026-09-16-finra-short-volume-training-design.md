# FINRA Daily Short-Volume Training Feasibility Design

Design decision: proceed under the user's standing instruction to continue
research autonomously. This is a distinct, training-only information contract;
it does not extend any exhausted OHLCV, quote, trade-print, or news family.

## Purpose

Test whether prior-session off-exchange short-sale flow contains a causal,
cross-sectional intraday selection edge in the existing full-market event
universe. FINRA Daily Short Sale Volume is transaction flow, not short interest,
borrow utilization, or a directional position measure. Every report and feature
name must preserve that distinction.

No strategy version is allocated during acquisition or training feasibility.
No development, consumed, Paper, broker, submit, or cancel path is permitted.

## Alternatives Considered

1. **Consolidated NMS daily files with official publication metadata (chosen).**
   This is free, full-market, compact, auditable, and economically distinct.
2. **FINRA query API.** Rejected for the first contract because bulk pagination
   adds authentication/rate-limit state without improving the underlying data.
3. **Monthly transaction files.** Deferred because their delayed publication
   makes causal availability and file volume materially more complex.
4. **Vendor short interest, borrow, or options data.** Deferred because it needs
   a separate licensed-data decision and cannot be silently substituted for the
   public FINRA flow contract.

## Authoritative Source and Semantics

For each trading date `YYYYMMDD`, acquire only:

`https://cdn.finra.org/equity/regsho/daily/CNMSshvolYYYYMMDD.txt`

The expected pipe-delimited schema is:

`Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market`

The final line is the provider row count and is not a security record. The
Consolidated NMS file aggregates exchange-listed securities reported to FINRA
TRFs and the ADF. It does not contain exchange-executed activity, undisclosed
activity, or short positions. Ratios therefore describe the FINRA-reported
off-exchange flow only.

The downloader records URL, HTTP status, response SHA-256, ETag when present,
Last-Modified, byte count, parsed row count, footer count, acquisition time,
and every rejection reason. Raw files, manifests, caches, and checkpoints stay
outside Git.

## Causal Availability and Corrections

FINRA states that daily files are posted no later than 18:00 ET on the trade
date and may rarely be updated later. The historical body currently available
is usable only from the response's official `Last-Modified` timestamp onward.

For an event at `decision_cutoff`, source date `d` is eligible only when:

1. `d < event session_date`;
2. `Last-Modified < decision_cutoff`;
3. the body and footer validate completely; and
4. no later source date is skipped and silently treated as zero.

A later correction is never backdated. If a 2021 file was republished in May
2021, it cannot contribute to January 2021 decisions. Missing or invalid
Last-Modified fails closed. The feature builder left-joins onto every event key;
missing data remains null with a reason and is never converted to zero or cash.

## Training-Only Acquisition Probe

The first implementation acquires only 2021-01-01 through 2023-12-31 sessions
present in the frozen event cache. It must:

- request one immutable daily file per expected prior session;
- retry transport and 429/5xx failures with bounded backoff;
- validate header, trade date, numeric non-negativity, `ShortVolume <= TotalVolume`,
  unique exact `(Date, Symbol)` keys, and footer count;
- preserve exact provider symbols without uppercase or punctuation normalization;
- publish partitions atomically only after validation;
- produce a coverage audit before any return computation.

The coverage gate requires at least 95% of eligible event rows to have a valid,
causally available exact-symbol prior-session observation and at least 500
covered sessions spanning all three training years. Any symbol collision,
duplicate key, malformed row, or unexplained missing session blocks research.

## Frozen Features

All features use only the latest causally available source session strictly
before the event session:

- `short_ratio = ShortVolume / TotalVolume`;
- `short_exempt_ratio = ShortExemptVolume / TotalVolume`;
- exact FINRA off-exchange `TotalVolume` and its log transform;
- 5- and 20-source-session trailing means and deviations of short ratio;
- 20-session within-symbol z-score, requiring at least 10 observations;
- source-session cross-sectional percentiles of ratio, deviation, and volume;
- one-session change in short ratio;
- interaction with the source session's signed close-to-close return, computed
  from the existing immutable bar contract without filling missing bars.

No feature uses the event session's FINRA file. Rolling windows ignore nulls but
never replace them; each output includes valid-observation counts.

## Frozen Training Feasibility Grid

Five economically distinct families are evaluated on 2021-2023 only:

1. abnormal-high short-flow reversal after a negative source-session return;
2. abnormal-high short-flow continuation after a positive source-session return;
3. short-ratio acceleration reversal;
4. short-exempt stress reversal;
5. high off-exchange participation with short-flow divergence.

Use decision bars 2, 5, 11, 17, and 23; holding bars 1, 2, 4, and 6; and top
counts 1, 3, 5, and 10, for exactly 400 cells. Every decision clock jointly
ranks all causally covered point-in-time eligible symbols. Portfolios are
long-only, equal-weighted, gross exposure at most one, and flat before close.

Each cell is frozen under standard 9 bp round-trip cost, 18 bp stress, and a
five-minute delayed-entry 9 bp stress. A cell is retained only if it has at
least 120 signal sessions, standard annualized return at least 20%, information
ratio at least 0.8, maximum drawdown below 20%, at least two positive calendar
years, positive 18 bp return, and positive delayed return.

Development acquisition is allowed only if retained cells span at least two
families. Otherwise the contract is abandoned without creating a strategy
version. Passing training feasibility is not strategy admission.

## Failure Handling and Evidence

- 404 on an expected market session remains a missing partition, not an empty file.
- Schema, footer, duplicate, date, or volume violations quarantine the body.
- Interrupted downloads leave no accepted partial partition.
- The run resumes from content-addressed accepted partitions.
- Reports publish counts and hashes, not raw data.
- `order_route` is always `FORBIDDEN`; `paper_activation` is always false.

## Verification

Tests must cover parsing and footer validation, exact-symbol preservation,
causal `Last-Modified` gating, corrections, missing sessions, retry/resume,
atomic publication, rolling-window null handling, exact event-key preservation,
400-cell cardinality, retention gates, training-date rejection, and absence of
broker or Paper state mutation.
