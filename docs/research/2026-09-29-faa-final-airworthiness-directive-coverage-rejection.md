# FAA final Airworthiness Directive coverage rejection

Decision: **ABANDON_FAA_FINAL_AD_COVERAGE_GATE**. The exact preregistered Federal Register inventory and all 687 official GovInfo PDFs were acquired and hash-frozen, but a deliberately permissive all-current-SEC upper-bound audit still produced only 14 issuers with at least three documents, below the frozen minimum of 15. Strict Type Certificate Holder mapping to the frozen 527-symbol sample can only be smaller. The event cube was not opened and no post-publication return was read.

## Immutable source accounting

The preregistered family retains only titles beginning `Airworthiness Directives;`, API type `Rule`, action exactly `Final rule.`, and abstracts without the stem `supersed`. It contains 687 documents: 287 in 2021, 225 in 2022, and 175 in 2023.

Every retained `pdf_url` was fetched sequentially from the official GovInfo Federal Register path. The corpus contains 687 valid PDFs, zero failures, 176,931,833 bytes, and 687 distinct SHA-256 values. The deterministic PDF manifest SHA-256 is `fd2f7e336c59deb6f87eac334f2315b6a58042ac1a7950b013895418ca7f1c0c`. No public-inspection draft, FAA DRS rendition, FederalRegister.gov HTML, snippet, service bulletin, or substituted endpoint was used.

## Fail-closed mapping upper bound

The official current SEC company-ticker snapshot contains 10,428 rows and has SHA-256 `016ae8ffe06c0f8f8bed5aff9af1bb69ae12b197a3441851c712f88a5d7f64f1`. It was used only to construct a universe broader than the frozen 527 identities. After the frozen mechanical punctuation/legal-suffix canonicalization, 7,994 keys were unique by SEC title and CIK.

For a deliberately permissive ceiling, every unique current-SEC key appearing anywhere in the complete AD title plus abstract was counted. This is much broader than the preregistered rule, which permits only the current affected Type Certificate Holder from the title/applicability text. The ceiling deliberately retains subsidiaries/parents, historical or background mentions, multiple share classes, and obvious common-word lexical matches such as `BOX`, `RH`, `Root`, `JOINT`, `ANGLE`, and `111` that strict mapping must reject.

The reproducible upper-bound artifact has SHA-256 `d06713cd8b6812f268164b6ea24efb2757445c0bb2a4bdbe85f7f3b18cfcccf7` and reports:

- 28 current-SEC issuers;
- 342 current-SEC symbol-document pairs;
- 131 / 128 / 83 symbol-document pairs in 2021 / 2022 / 2023;
- 24 / 18 / 16 current-SEC issuers in 2021 / 2022 / 2023;
- only **14 issuers with at least three documents**, versus the frozen requirement of 15.

Because the audit covers all current SEC issuers rather than the frozen sample and searches title plus abstract rather than the strict holder field, applying the frozen 527 membership, current-holder role, one-to-one identity, and ambiguity rules cannot create a fifteenth qualifying issuer. Calendar mapping cannot repair that monotone shortfall. The strict frozen mapping was therefore not executed. No brand, product, model, division, subsidiary-to-parent inference, former name, acronym, fuzzy match, or hand-written alias was introduced to rescue the line.

Final state: `source_complete=true`, `training_pdf_inventory_acquired=true`, `all_current_sec_upper_bound_audit=true`, `frozen_527_mapping_performed=false`, `event_cube_opened=false`, `cells_completed=0`, `post_availability_outcomes_loaded=false`. The family, source filters, and coverage thresholds are frozen and may not be reopened. No development or consumed period, strategy version, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.
