# FDA human-drug patent-term-extension review-period source audit and coverage preregistration

Status: **SOURCE_FEASIBLE_AND_COVERAGE_PREREGISTERED**. This stage used official publication metadata and official statutory-process documentation only. It did not acquire the 103 GovInfo PDFs, map applicants, open the frozen event cube, or read any post-publication return. The sample remains a **527-symbol coverage-limited sample, not the full US market**.

## Official event and point-in-time contract

Under 35 U.S.C. 156, FDA determines the length of the regulatory review period for an approved product after USPTO receives a patent-term-extension application. USPTO states that FDA publishes the testing and approval periods in the Federal Register; the determination supplies inputs that USPTO later uses to determine actual extension eligibility and length. The publication starts windows for requesting redetermination and filing due-diligence petitions, and the FDA period is not final until those processes expire or are resolved. This is therefore a positive procedural and quantified patent-duration input for the expressly named patent-term-extension applicant, not a patent-extension grant and not a claim that an extension will issue.

Only the official GovInfo publication PDF corresponding to the Federal Register `document_number` is admissible content. Availability is the first frozen-sample trading session strictly after `publication_date`. Public-inspection drafts, FederalRegister.gov HTML, product databases, patent files, press coverage, and later consolidated copies may not replace the official publication PDF.

Official references:

- Federal Register API: https://www.federalregister.gov/developers/documentation/api/v1
- Official Federal Register collection: https://www.govinfo.gov/app/collection/FR
- USPTO regulatory-agency review-period process: https://www.uspto.gov/web/offices/pac/mpep/s2757.html
- USPTO final extension calculation: https://www.uspto.gov/web/offices/pac/mpep/s2758.html
- FDA Patent Term Restoration FAQ: https://www.fda.gov/drugs/cder-small-business-industry-assistance-sbia/small-business-assistance-frequently-asked-questions-patent-term-restoration-program

## Frozen metadata inventory

The exact query fixes agency `food-and-drug-administration`, publication dates 2021-01-01 through 2023-12-31, full-text term `Determination of Regulatory Review Period for Purposes of Patent Extension`, ascending order, and `per_page=1000`. Its raw official API response is stored only under ignored `state/research/fda_pte_review_period_source_audit/federal-register-api.json`: 406,578 bytes, SHA-256 `a1c787cb19f47a9ab1037de56618559235897b772c6280df810e98361925e887`.

The API reports 159 search results, of which 156 titles begin exactly `Determination of Regulatory Review Period for Purposes of Patent Extension;`. The economically homogeneous candidate is frozen before applicant matching as:

1. title begins exactly `Determination of Regulatory Review Period for Purposes of Patent Extension;`;
2. API type equals `Notice`;
3. title does not end in `; Correction`;
4. abstract contains the exact case-insensitive phrase `human drug product`.

This leaves 103 original human-drug determinations: 27 in 2021, 21 in 2022, and 55 in 2023. The remaining records include medical devices, human biologics, a non-human-drug residual, and corrections. All 103 retained metadata rows have document number, publication date, abstract, type, and official GovInfo PDF URL; document numbers are unique. Medical devices, biologics, veterinary products, corrections, patent-extension grants, petitions, and approval announcements are excluded and may not be added later.

## Causal exposure and strict entity contract

A qualifying notice is a positive procedural event only for the complete legal entity expressly identified in the official PDF as the applicant for patent-term extension. A marketing applicant, product sponsor, patent owner, assignee, agent, or application holder mentioned in another role is not substituted. Mapping is allowed only when that complete legal name is mechanically equal, after the already frozen conservative punctuation and legal-suffix normalization, to exactly one frozen SEC issuer identity. Product and brand names, patent or application numbers, agents, subsidiaries, parents, affiliates, former names, abbreviations, fuzzy matches, and hand-written aliases are forbidden. Multiple, missing, or ambiguous applicant identities are explicit rejections.

## Coverage gate frozen before document acquisition

The line advances to training only if the metadata-only strict mapping satisfies every condition:

- at least 10 distinct frozen-sample issuers;
- at least 50 distinct symbol-document pairs;
- at least 12 pairs in each of 2021, 2022, and 2023;
- at least 5 distinct issuers in each year;
- at least 6 issuers with three or more qualifying documents;
- no single issuer contributes more than 25% of all qualifying pairs;
- every retained document maps to an available next frozen-sample trading session.

The exact official API response and every retained GovInfo PDF must be hash-frozen. Missing PDFs, non-PDF payloads, duplicate document numbers, correction conflicts, an applicant-role ambiguity, or an unavailable next session fail closed. The coverage audit may inspect only publication metadata, official PDF content needed for applicant extraction, frozen issuer identities, and the trading calendar; it may not load post-publication returns.

If any gate fails, record `ABANDON_FDA_HUMAN_DRUG_PTE_COVERAGE_GATE`, keep `cells_completed=0`, freeze the line, and move to a genuinely different source without changing filters, entity rules, or thresholds. Only after every coverage gate passes may the 400-cell 9/18 bp training grid and one delayed-availability tier be frozen and executed. Passing training would only justify requesting development data, not Paper activation.

Current state: `source_feasible=true`, `coverage_preregistered=true`, `api_metadata_acquired=true`, `human_drug_document_count=103`, `human_drug_year_counts=27/21/55`, `training_pdf_inventory_acquired=false`, `applicant_mapping_performed=false`, `event_cube_opened=false`, `cells_completed=0`, `post_publication_outcomes_loaded=false`. No development or consumed period, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.
