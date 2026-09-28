# USITC Section 337 Institution Notices: Coverage Rejection

## Decision

Freeze this source as `ABANDON_USITC_SECTION337_COVERAGE_GATE`. The training event cube was not opened for outcomes, no post-availability return column was loaded, and `cells_completed=0`.

This decision applies only to the frozen 2021-2023 sample of 527 symbols. That sample is coverage-limited and is not the full US equity market.

## Frozen source inventory

- The preregistered Federal Register API response reproduced 148 unique raw records and the frozen literal-title rule retained 145 notices, split 50/60/35 by publication year.
- All 145 retained official GovInfo PDFs were acquired without failure. They contain 27,850,274 bytes in total and 145 distinct SHA-256 values.
- The Federal Register API payload SHA-256 is `0c860f90ac91dd39862b5e7990e14025a10110a0e270bfed9e60581b78f44f32`.
- The PDF acquisition manifest SHA-256 is recorded by the coverage audit. The final coverage audit manifest SHA-256 is `44e22e8acc1e0d71a1b95f2d44bfdbfe47515766fd78134ecb0c7215300f848c`.
- The event cube and SEC identity inputs matched their preregistered hashes. Only `symbol` and `session_date` were loaded from the event cube.

## Fail-safe upper-bound audit

Strict respondent extraction was unnecessary because a deliberately permissive superset already failed hard gates. For each notice, the audit accepted an exact frozen SEC issuer-title key appearing anywhere from the target notice's `Scope of Investigation` heading through its own FR Doc marker. It retained ambiguous SEC keys, complainants, background mentions, and accidental lexical matches. For the seven PDFs without a recoverable target scope heading, it broadened the search further to all extracted text before the target FR Doc marker.

This permissive upper bound found:

- 50 distinct frozen-sample issuers;
- 93 symbol-document pairs across 56 notices;
- 32/50/11 symbol-document pairs in 2021/2022/2023;
- family event counts of 4 communications/wireless, 47 semiconductor/computing, 0 medical/life-science, 3 consumer/home, and 39 industrial/materials/other;
- family next-session-date counts of 4, 24, 0, 3, and 26 in the same order.

The upper bound fails the frozen minimum of 15 symbol-document events in every year because 2023 has at most 11. It also fails the frozen event and date minimums for multiple title families. The preregistered strict respondent-only, one-to-one mapping is a subset of this upper bound, so it cannot pass any failed upper-bound threshold.

## Frozen consequences

- Do not perform strict respondent extraction or map brands, products, complainants, patent owners, importers, parents, subsidiaries, former names, abbreviations, fuzzy names, or manual aliases to rescue this source.
- Do not add termination, modification, rescission, remand, enforcement, advisory, temporary-relief, review, or merits notices.
- Do not redefine the five title families, lower thresholds, extend the training window, or change the frozen sample after observing coverage.
- Do not load any post-availability outcome or preregister/run the 400-cell return grid for this source.

The next research line must use a genuinely different free official event family with an auditable public timestamp, immutable official content identity, and structurally adequate strict issuer coverage before outcomes are read.
