# EPA pesticide cancellation-order source rejection

Decision: **ABANDON_EPA_PESTICIDE_CANCELLATION_ORDER_VOLUME_GATE**. The proposed 2021-2023 Federal Register EPA pesticide cancellation-order line is frozen at the source-volume/design gate, before PDF acquisition, registrant matching, event-cube access, or any post-publication return read. This is a statutory pesticide-registration family distinct from the already frozen EPA administrative-settlement family. The frozen event cube remains a **527-symbol coverage-limited sample, not the full US market**.

## Fixed homogeneous family

The contemplated family was a final EPA order accepting voluntary cancellation of pesticide product registrations under FIFRA, published as `Product Cancellation Order for Certain Pesticide Registrations` or the equivalent generic `Cancellation Order for Certain Pesticide Registrations`. Notices of receipt or intent, voluntary cancellation requests, registration applications, tolerance actions, maintenance-fee orders, use terminations, active-ingredient-specific actions, enforcement settlements, corrections, amendments, rescissions, and other FIFRA actions were excluded before issuer overlap was examined.

## Official metadata count

The Federal Register API query fixed EPA as the issuing agency, publication dates from 2021-01-01 through 2023-12-31, and the term `pesticide cancellation order`. It returned 74 search results. Even a deliberately overinclusive title upper bound containing `Cancellation Order` admitted only 35 documents, distributed 15/10/10 in 2021/2022/2023. That upper bound still includes legally different use-termination, maintenance-fee, active-ingredient-specific, correction, amendment, and rescission documents.

Applying the predeclared generic final-product-order title family leaves only 12 documents: 6/3/3 in 2021/2022/2023. It therefore fails the fixed high-frequency source floor of 100 total events and 20 events in every training year. Counting each product registration, registrant row, or ingredient inside one Federal Register order as an independent publication event would manufacture pseudo-events and is forbidden.

Official sources:

- https://www.federalregister.gov/api/v1/documents.json?conditions%5Bagencies%5D%5B%5D=environmental-protection-agency&conditions%5Bpublication_date%5D%5Bgte%5D=2021-01-01&conditions%5Bpublication_date%5D%5Blte%5D=2023-12-31&conditions%5Bterm%5D=pesticide%20cancellation%20order&per_page=1000&order=oldest
- https://www.federalregister.gov/developers/documentation/api/v1
- https://www.govinfo.gov/app/collection/FR

Federal Register `publication_date`, document number, and the corresponding GovInfo PDF provide a potentially auditable public-time and immutable-document design, but document volume fails before corpus acquisition or correction-chain verification is warranted. No API response or PDF corpus was persisted.

Final state: `source_volume_gate_passed=false`, `preregistered=false`, `api_response_persisted=false`, `govinfo_pdf_inventory_acquired=false`, `registrant_mapping_performed=false`, `event_cube_opened=false`, `cells_completed=0`, `post_publication_outcomes_loaded=false`. Do not reopen by mixing excluded FIFRA actions, treating table rows as separate releases, or mapping products, trade names, registration numbers, agents, subsidiaries, parents, former names, abbreviations, fuzzy matches, or manual aliases. No development or consumed period, strategy version, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.
