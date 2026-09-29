# FAA final Airworthiness Directive source audit and coverage preregistration

Status: **SOURCE_FEASIBLE_AND_COVERAGE_PREREGISTERED**. This stage used official publication metadata only. It did not acquire the GovInfo PDF corpus, map manufacturers to the frozen 527-symbol sample, open the event cube, or read any post-publication return. The sample remains coverage-limited and is not the full US market.

## Official event and point-in-time contract

The FAA states that Airworthiness Directives (ADs) are legally enforceable rules under 14 CFR part 39, that a normal final AD is published in the Federal Register, and that the AD subject line identifies the affected product's Type Certificate Holder. FederalRegister.gov exposes the publication metadata and official GovInfo PDF URL, while warning that its own XML/HTML rendition is informational rather than the official legal edition.

Only the official GovInfo publication PDF is admissible content. The event identifier is the stable Federal Register `document_number`; availability is the first frozen-sample trading session strictly after `publication_date`. Public-inspection drafts, FAA DRS renditions, HTML, snippets, service bulletins, and later consolidated copies may not replace the official publication PDF.

Official references:

- FAA AD authority and publication process: https://www.faa.gov/aircraft/air_cert/continued_operation/ad/gen_resp
- FAA AD applicability and Type Certificate Holder subject-line rule: https://www.faa.gov/aircraft/air_cert/continued_operation/ad/app_comp
- FAA AD types and supersession: https://www.faa.gov/aircraft/air_cert/continued_operation/ad/type_pub
- Federal Register API and legal-status warning: https://www.federalregister.gov/developers/documentation/api/v1
- Official Federal Register collection: https://www.govinfo.gov/app/collection/FR

## Frozen metadata inventory

The exact query fixes agency `federal-aviation-administration`, document type `RULE`, publication dates 2021-01-01 through 2023-12-31, full-text term `Airworthiness Directives`, ascending order, `per_page=1000`, and fields `document_number,title,type,publication_date,action,abstract,pdf_url`. Two official API pages were saved only under ignored `state/research/faa_ad_source_audit/`:

- page 1: 1,016,289 bytes; SHA-256 `9b8429045d6527855eda2b1c2dfd29d76ccd3e08837f8935b3cafae7e8720a6d`;
- page 2: 286,358 bytes; SHA-256 `43873708bd2c09f1e5a3a49d396c05eba1aec95bacd3f9200c7de1026e07c154`.

The API reports 1,267 records; 1,261 have titles beginning exactly `Airworthiness Directives;`. Their actions are 952 `Final rule.`, 288 `Final rule; request for comments.`, 13 `Final rule; correction.`, four removals, two removals with requests for comments, and two request-for-comment corrections.

The economically homogeneous candidate is fixed before issuer matching as:

1. title begins exactly `Airworthiness Directives;`;
2. API type is `Rule`;
3. action equals exactly `Final rule.`;
4. abstract does not contain the case-insensitive stem `supersed`.

This excludes NPRMs, immediately adopted/emergency rules later published with requests for comments, corrections, removals, and superseding directives whose information shock is incremental to an earlier AD. The resulting gross inventory is 687 documents: 287 in 2021, 225 in 2022, and 175 in 2023. Corrections remain linked evidence but are not separate events. Missing action, abstract, document number, publication date, or official PDF URL is a hard rejection, never an imputation.

## Causal exposure and strict entity contract

A qualifying final AD is a negative issuer event only for the legal Type Certificate Holder named in the AD title/applicability text. Mapping is allowed only when that full legal entity name is mechanically equal, after the already frozen conservative legal-suffix/punctuation canonicalization, to exactly one frozen SEC issuer identity. Product names, aircraft or engine models, brands, divisions, subsidiaries, parents, former holders, acronyms, fuzzy matches, and hand-written aliases are forbidden. Titles naming multiple or historical holders are rejected unless the current affected holder alone is stated and exactly matches one frozen issuer. Unmatched and ambiguous documents remain explicit misses.

## Coverage gate frozen before matching

The line advances to training only if the metadata-only strict mapping satisfies every condition:

- at least 20 distinct frozen-sample issuers;
- at least 300 distinct symbol-document pairs;
- at least 75 pairs in each of 2021, 2022, and 2023;
- at least 10 distinct issuers in each year;
- at least 15 issuers with three or more qualifying documents;
- no single issuer contributes more than 25% of all qualifying pairs;
- every retained document maps to an available next sample trading session.

The complete official API responses and every retained official GovInfo PDF must be hash-frozen. Pagination mismatch, duplicate document numbers, missing PDFs, non-PDF payloads, correction ambiguity, or an unresolvable title/applicability conflict is recorded and fails closed. The coverage audit may inspect only publication metadata, PDF identity/content needed for holder extraction, frozen issuer identities, and the trading calendar; it may not load any post-availability return.

If any gate fails, record `ABANDON_FAA_FINAL_AD_COVERAGE_GATE`, keep `cells_completed=0`, freeze the line, and move to a genuinely different source without changing filters or thresholds. Only after all coverage gates pass may the fixed 400-cell training grid, 9/18 bp costs, and one delayed-availability tier be specified and executed. Passing training would only justify requesting development data, not Paper activation.

Current state: `source_feasible=true`, `coverage_preregistered=true`, `api_metadata_acquired=true`, `training_pdf_inventory_acquired=false`, `issuer_mapping_performed=false`, `event_cube_opened=false`, `cells_completed=0`, `post_availability_outcomes_loaded=false`. No development or consumed period, strategy version, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.
