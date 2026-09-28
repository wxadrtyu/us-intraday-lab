# Federal Register Consent-Decree Training Design

## Scope and causal hypothesis

This is a versionless, training-only feasibility screen on the fixed 527 symbols in the frozen 2021–2023 event cube: a **coverage-limited sample, not the full US market**. It tests whether official publication of an environmental consent-decree notice identifies a short-lived, long-only overreaction state among exact-mapped defendants. A consent decree is an adverse enforcement resolution, so the only authorized long-only mechanism is bounded mean reversion after a negative observed response. No short sale, peer trade, sector proxy, avoidance overlay, or later-period rank is authorized.

## Exact official source and availability

The discovery source is the Federal Register API query with all of these fixed conditions: agency slug `justice-department`, `publication_date.gte=2021-01-01`, `publication_date.lte=2023-12-31`, term `consent decree`, `per_page=1000`, and result titles containing the case-insensitive literal `Consent Decree`. Acquire the raw API response once after this preregistration and preserve the requested URL, retrieval UTC, response headers, bytes, SHA-256, returned count, pagination fields, and all records. Reject pagination, count, or duplicate-document-number inconsistencies rather than silently repairing them.

For each retained document number, the sole content authority is the official GovInfo granule PDF at the API `pdf_url`. The PDF must resolve under `https://www.govinfo.gov/content/pkg/FR-YYYY-MM-DD/pdf/<document_number>.pdf`, match the API publication date and document number, and be preserved with response headers, bytes, SHA-256, and any available GovInfo package/PREMIS fixity metadata. FederalRegister.gov HTML/text/XML, public-inspection PDFs, DOJ library copies, and search snippets are locator or audit material only.

Availability begins on the first frozen-sample trading session strictly after printed `publication_date`; the prior-day public-inspection time is intentionally ignored. An official correction, amendment, modification, extension, or later decree is a separate audit record and cannot rewrite an earlier PDF. The signal expires after five sample sessions.

## Exact defendant mapping

Extract only a complete legal entity expressly named as a defendant or settling party in the official notice's case caption or first description of the lodged decree. Normalize that string and the already frozen SEC issuer title mechanically by Unicode NFKC, uppercase, ampersand-to-AND, punctuation-to-space, whitespace collapse, and removal of one terminal suffix from the fixed set `INC`, `INCORPORATED`, `CORP`, `CORPORATION`, `CO`, `COMPANY`, `LLC`, `LTD`, `LIMITED`, `PLC`, `LP`, `LLP`, `SA`, `NV`. Accept only one-to-one normalized equality.

Reject `et al.`, collective labels, incomplete names, individuals, governments, municipalities, facilities, brands, trade names, former names, acronyms, subsidiaries, parents, successors, affiliates, d/b/a names, and entities appearing only in background prose. Do not use fuzzy similarity, addresses, facilities, tickers, web searches, manual aliases, or model-generated identities. Preserve every unmatched, ambiguous, incomplete, and multi-defendant case. One notice may yield multiple exact symbol events only when each legal entity independently passes the same rule.

## Five frozen title families and signal score

Normalize the title by Unicode NFKC, uppercase, punctuation-to-space, and whitespace collapse, then assign the first matching family in this fixed priority order:

1. `clean_air`: contains `CLEAN AIR ACT` and none of `CLEAN WATER ACT`, `OIL POLLUTION ACT`, `COMPREHENSIVE ENVIRONMENTAL RESPONSE`, `RESOURCE CONSERVATION AND RECOVERY ACT`, or `TOXIC SUBSTANCES CONTROL ACT`.
2. `clean_water_oil`: contains `CLEAN WATER ACT` or `OIL POLLUTION ACT`, unless already assigned.
3. `cercla`: contains `COMPREHENSIVE ENVIRONMENTAL RESPONSE` or `CERCLA`, unless already assigned.
4. `waste_chemicals`: contains `RESOURCE CONSERVATION AND RECOVERY ACT`, `TOXIC SUBSTANCES CONTROL ACT`, `SAFE DRINKING WATER ACT`, or `EMERGENCY PLANNING AND COMMUNITY RIGHT TO KNOW ACT`, unless already assigned.
5. `general_multi_other`: every remaining title containing `CONSENT DECREE`, including amendments, modifications, corrections, extensions, generic lodging titles, and other statutes.

Each document number is assigned once. On each active session, require the exact-mapped symbol's strictly prior sample-session finite `bar_idx=5` `session_return` to be below zero. Score is its negative prior return descending, with symbol ascending as the exact tie break. Multiple active notices for one symbol remain one signal using the highest-priority family and earliest document number; preserve the collision inventory.

## Coverage gate before outcomes

Before opening any post-availability return column, require:

- a complete hash-frozen raw API response and one unique official GovInfo PDF URL for every retained document number;
- all 255 source-screen document numbers accounted for as retained or explicitly rejected, with 96/81/78 records by API publication year reproduced exactly;
- all three training years represented by exact-mapped events;
- at least 50 distinct exact-mapped frozen issuers and at least 200 unique exact symbol-document events;
- at least 20 exact symbol-document events and at least 8 events in each training year for every family;
- at least 20 distinct next-session availability dates per family after calendar mapping;
- complete accounting of API/source failures, duplicate IDs, nonconforming URLs, PDF identity failures, corrections/amendments/modifications/extensions, incomplete captions, unmatched and ambiguous names, multi-defendant cases, family assignments, calendar losses, nonnegative prior returns, and missing prior bar-5 returns.

Failure freezes `ABANDON_FEDERAL_REGISTER_CONSENT_DECREE_COVERAGE_GATE`, `cells_completed=0`, and no post-availability outcomes. Do not alter the query, merge or redefine families, relax normalization, add aliases, treat background mentions as defendants, extend signal life, or lower thresholds after observing coverage.

## Frozen 400-cell diagnostic and terminal rule

Only if every coverage requirement passes, evaluate five families × decision bars `(2,5,11,17,23)` × holding bars `(1,2,4,6)` × top counts `(1,3,5,10)` = exactly 400 cells. Standard cost is 9 bp; stress cost is 18 bp; the sole delay test enters one bar later at 9 bp. A zero-signal session is flat. A selected missing outcome is invalid, never cash, zero return, forward-filled, or substituted.

A retained cell requires at least 40 observed signal sessions and at least 10 in each training year, full-calendar annualized 9 bp net return at least 20%, IR at least 0.8, maximum drawdown below 20%, at least two positive calendar years, and positive annualized return under both 18 bp and one-bar delay. Require retained cells in at least two families. Passing training yields only `ACQUIRE_DEVELOPMENT_FEDERAL_REGISTER_CONSENT_DECREE_DATA`; failure yields `ABANDON_FEDERAL_REGISTER_CONSENT_DECREE_NO_VERSION_CREATED`. No development or consumed period is loaded for ranking. No broker, submit/cancel, Paper activation, pool mutation, order route, or shutdown is authorized.
