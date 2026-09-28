# FDA Warning-Letter Training Design

## Scope and causal hypothesis

This is a versionless, training-only feasibility screen on the fixed 527 symbols in the frozen 2021–2023 event cube: a **coverage-limited sample, not the full US market**. It tests whether the first public FDA posting of a significant regulatory warning identifies a short-lived, long-only overreaction state among exact-mapped recipients. It is not a retry of Drugs@FDA approval actions: Warning Letters are enforcement communications, and the public posting date is separately recorded from the private letter-issue date.

FDA states that Warning Letters concern violations of regulatory significance. The direct enforcement implication is adverse, which a long-only portfolio cannot express as continuation. The only preregistered trade mechanism is therefore a bounded mean-reversion hypothesis after negative price response; no short sale, peer inference, sector substitution, or avoidance overlay is authorized.

## Official source and availability

The sole index source is FDA's [Warning Letters page](https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/compliance-actions-and-activities/warning-letters) and its official XLSX export endpoint:

`https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/compliance-actions-and-activities/warning-letters/datatables-data?_format=xlsx&page=`

The export must be fetched once, sequentially, after this preregistration. Preserve request URL, retrieval UTC, response headers, bytes, SHA-256, workbook sheet names, original rows, and a normalized snapshot. Only rows with `Posted Date` in 2021-01-01 through 2023-12-31 are training source records. `Posted Date`, not `Letter Issue Date`, is public availability. The first usable session is the first frozen-sample trading session strictly after Posted Date; this avoids assuming a posting time. Each signal expires after five sample sessions.

FDA's Regulatory Procedures Manual says issued Warning Letters should be publicly posted after redaction and that FDA does not remove them unless it rescinds or amends the letter. This supports using the current issued-letter text as the official public document, but every training row must retain its current URL and content hash. Exclude a rescinded/amended marker, missing URL, missing posted or issue date, posted-before-issue date, duplicate CMS identifier, or conflicting duplicate URL. Response and closeout letters are later state and are audit-only; they may not alter the original event or family.

## Exact issuer mapping

Use the already frozen SEC issuer-title identity source underlying the 527-symbol sample. Normalize FDA `Company Name` and SEC issuer title mechanically by Unicode NFKC, uppercase, ampersand-to-AND, punctuation-to-space, whitespace collapse, and removal of a terminal legal suffix only from the fixed set `INC`, `INCORPORATED`, `CORP`, `CORPORATION`, `CO`, `COMPANY`, `LLC`, `LTD`, `LIMITED`, `PLC`, `LP`, `LLP`, `SA`, `NV`. Accept only a one-to-one normalized equality. If either side maps to multiple distinct entities, reject every ambiguous match.

No brand, website, product, address, officer, FEI, subsidiary, parent, acronym, former name, foreign translation, fuzzy similarity, manual override, or model-generated alias may create a match. Preserve every unmatched and ambiguous row. A company named in a response, closeout, inspection description, or product text is not an event recipient.

## Five frozen families and signal score

Classify the index `Subject` after uppercase punctuation-to-space normalization, assigning the first matching family in this fixed priority order:

1. `clinical_research_integrity`: contains `CLINICAL INVESTIGATOR`, `INSTITUTIONAL REVIEW BOARD`, `BIOEQUIVALENCE`, `DATA INTEGRITY`, or `RESEARCH`.
2. `tobacco_ends`: contains `TOBACCO`, `ENDS`, `E CIGARETTE`, or `VAPE`.
3. `food_supplier_controls`: contains `FSVP`, `HACCP`, `PREVENTIVE CONTROL`, `FOREIGN SUPPLIER`, or `FOOD`.
4. `unapproved_misbranded`: contains `UNAPPROVED`, `MISBRAND`, `MARKETING`, or `PROMOTION`.
5. `manufacturing_quality`: contains `CGMP`, `CURRENT GOOD MANUFACTURING`, `QUALITY SYSTEM`, `ADULTERAT`, or `MANUFACTURING`.

Rows matching no family are source-audit only. A row matching multiple families stays in the first priority family; no multi-counting is allowed. On each active session, require the recipient's strictly prior sample-session finite `bar_idx=5` `session_return` to be below zero. Score is its negative prior return, descending, with symbol ascending as the exact tie break. Take only unique symbols, equal weight, long only, no overnight carry beyond the frozen holding bars. Multiple letters for one symbol on one posted date remain one symbol signal with the highest-priority family; preserve the collision in audit output.

## Coverage gate before outcomes

Before opening any post-availability return column, require:

- one complete, hash-frozen official XLSX response with all required columns and no unresolved duplicate key;
- all three training years represented by both posted dates and exact-mapped events;
- at least 100 distinct exact-mapped frozen issuers;
- at least 500 unique exact-mapped symbol-letter events;
- at least 50 exact-mapped events in each family and at least 10 per family in each training year;
- at least 40 distinct availability sessions per family after calendar mapping;
- complete accounting of source exclusions, invalid dates, duplicate CMS IDs/URLs, rescinded/amended markers, unmatched names, ambiguous names, unclassified subjects, calendar losses, nonnegative prior returns, and missing prior bar-5 returns.

Failure freezes `ABANDON_FDA_WARNING_LETTER_COVERAGE_GATE`, `cells_completed=0`, and no post-availability outcomes. Do not relax normalization, add aliases, merge families, extend signal life, or lower thresholds after seeing coverage.

## Frozen 400-cell diagnostic and terminal rule

Only if coverage passes, acquire and hash the exact linked training Warning Letter pages, verify recipient/company/date/CMS identity, and then evaluate five families × decision bars `(2,5,11,17,23)` × holding bars `(1,2,4,6)` × top counts `(1,3,5,10)` = exactly 400 cells. Standard cost is 9 bp; stress cost is 18 bp; the delay test enters one bar later at 9 bp. A zero-signal session is flat. A selected missing outcome is invalid, never cash, zero return, forward-filled, or substituted.

A retained cell requires at least 40 observed signal sessions and at least 10 in each training year, full-calendar annualized 9 bp net return at least 20%, IR at least 0.8, maximum drawdown below 20%, at least two positive calendar years, and positive annualized returns under 18 bp and one-bar delay. Require retained cells in at least two families. Passing training yields only `ACQUIRE_DEVELOPMENT_FDA_WARNING_LETTER_DATA`; failure yields `ABANDON_FDA_WARNING_LETTER_NO_VERSION_CREATED`. No development or consumed period is loaded for ranking. No broker, submit/cancel, Paper activation, pool mutation, order route, or shutdown is authorized.
