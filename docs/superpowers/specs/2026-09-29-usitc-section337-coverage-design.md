# USITC Section 337 Institution-Notice Coverage Design

## Scope and mechanism

This is a metadata-only coverage screen on the fixed 527 symbols in the frozen 2021-2023 event cube, a **coverage-limited sample, not the full US market**. The candidate event is official Federal Register publication of a USITC Section 337 investigation institution notice naming a listed issuer as a respondent. Institution creates a public, product-specific import-exclusion risk before any merits determination. Complainants, patents, products, suppliers, peers, and later case outcomes are not signals.

This checkpoint does not authorize any return read or strategy grid. If and only if the coverage gate passes, a later atomic preregistration must freeze the causal score, exact 400 cells, 9/18 bp costs, one-bar delay, performance gates, and terminal rule before outcomes are loaded.

## Exact official source and availability

Acquire once the raw Federal Register API response for agency slug `international-trade-commission`, `publication_date.gte=2021-01-01`, `publication_date.lte=2023-12-31`, term `"Institution of Investigation"`, oldest-first order, and `per_page=1000`. Preserve exact URL, retrieval UTC, headers, bytes, SHA-256, count, pagination, and every returned record. Require exactly 148 unique raw document numbers. Retain only titles containing the case-insensitive literal `INSTITUTION OF INVESTIGATION`; require exactly 145 retained unique document numbers and 50/60/35 retained records by publication year. Preserve the three expected false-positive exclusions `2021-09991`, `2022-16049`, and `2022-20575`; otherwise freeze a source-identity failure rather than changing the query or title rule.

For every retained document, the sole content authority is the API `pdf_url` under the official GovInfo Federal Register publication path. Preserve headers, bytes, SHA-256, PDF identity, and available GovInfo metadata. FederalRegister.gov renditions, public-inspection PDFs, USITC press releases, EDIS documents, and search snippets are locator or audit material only. Availability is the first frozen-sample trading session strictly after `publication_date`. Corrections and later notices remain separate records and cannot rewrite an earlier event.

Reject titles that do not denote institution of a Section 337 investigation. Do not add terminations, modifications, rescissions, remands, enforcement proceedings, advisory opinions, temporary relief, review, or final/merits determinations to increase coverage.

## Exact respondent mapping

Extract only complete legal entities expressly enumerated as **respondents** in the official notice's ordered scope-of-investigation section. Do not map complainants. Normalize respondent names and already frozen SEC issuer titles by Unicode NFKC, uppercase, ampersand-to-AND, punctuation-to-space, whitespace collapse, and removal of one terminal suffix from the fixed set `INC`, `INCORPORATED`, `CORP`, `CORPORATION`, `CO`, `COMPANY`, `LLC`, `LTD`, `LIMITED`, `PLC`, `LP`, `LLP`, `SA`, `NV`. Accept only one-to-one normalized equality.

Reject collective labels, `et al.`, incomplete names, individuals, brands, products, patent owners, complainants, importers that are not the issuer itself, trade names, former names, acronyms, subsidiaries, parents, affiliates, distributors, successors, and entities appearing only in background prose. Do not use fuzzy similarity, addresses, websites, tickers, manual aliases, or model-generated identities. Preserve every unmatched, ambiguous, incomplete, multi-respondent, and role-rejected entity. One notice may yield multiple symbol-document events only when each respondent independently passes the same rule.

## Five fixed product-title families

Normalize the title by Unicode NFKC, uppercase, punctuation-to-space, and whitespace collapse; then assign the first matching family in this priority order:

1. `communications_wireless`: contains `COMMUNICATION`, `WIRELESS`, `CELLULAR`, `LTE`, `5G`, `RADIO`, `ANTENNA`, or `NETWORK`.
2. `semiconductor_computing`: contains `SEMICONDUCTOR`, `INTEGRATED CIRCUIT`, `PROCESSOR`, `COMPUTER`, `MEMORY`, `DISPLAY`, or `ELECTRONIC`.
3. `medical_life_science`: contains `MEDICAL`, `SURGICAL`, `PHARMACEUTICAL`, `DRUG`, `DIAGNOSTIC`, `ASSAY`, or `DENTAL`.
4. `consumer_home`: contains `FOOTWEAR`, `APPLIANCE`, `FURNITURE`, `TOY`, `GRILL`, `VACUUM`, `BEVERAGE`, `FOOD`, or `COSMETIC`.
5. `industrial_materials_other`: every remaining retained institution notice.

Each document is assigned once. These families are frozen only for coverage accounting; they do not yet define a return signal.

## Coverage gate before outcomes

Before loading any post-availability return column, require:

- the hash-frozen raw API response, 148 unique raw document numbers, the three frozen title exclusions, 145 retained notices, exact 50/60/35 retained publication-year counts, and one unique conforming official GovInfo PDF per retained notice;
- all records accounted for as retained or explicitly rejected, with complete duplicate, correction, source-failure, PDF-identity, role, unmatched, ambiguity, multi-respondent, family, and calendar-loss inventories;
- all three publication years represented by exact-mapped frozen issuers;
- at least 25 distinct exact-mapped frozen issuers and at least 75 unique exact symbol-document events;
- at least 15 exact symbol-document events in each publication year;
- at least 8 exact symbol-document events and at least 5 distinct next-session availability dates in each family.

Failure freezes `ABANDON_USITC_SECTION337_COVERAGE_GATE`, `cells_completed=0`, and no post-availability outcomes. Do not alter the query, add later notices, merge or redefine families, relax roles or normalization, add aliases, extend the sample, or lower thresholds after observing coverage. Passing yields only `PREREGISTER_USITC_SECTION337_TRAINING_GRID`; it does not authorize development data, ranking, Paper activation, pool mutation, broker access, order routing, or shutdown.
