# USAspending contract-transaction source rejection

Decision: **ABANDON_USASPENDING_CONTRACT_PUBLICATION_HISTORY_GATE**. The proposed 2021-2023 USAspending federal contract transaction line is frozen at the public-availability and historical-version gates, before transaction acquisition, recipient matching, event-cube access, or any post-publication return read. The frozen event cube remains a **527-symbol coverage-limited sample, not the full US market**.

## Official source audit

USAspending documents that its site is refreshed after a nightly pipeline, while federal agencies generally submit contract actions to FPDS within three business days; data become available to USAspending the next day and are automatically published on the following day. Department of Defense and U.S. Army Corps of Engineers contract data can instead be delayed by 90 days. This proves that `action_date` is not public availability.

The current API exposes action date, last-modified date, award and transaction identifiers, modification number, and a correction/delete indicator. It does not expose a per-transaction first-publication timestamp or an immutable first-public version. The public API and bulk downloads represent current loaded state after nightly processing and upstream corrections. Neither `last_modified_date` nor a current correction/delete flag reconstructs the prior values visible on each historical publication day, and the official documentation does not provide a complete 2021-2023 transaction-version manifest with original bytes and publication timestamps.

Official sources:

- https://www.usaspending.gov/data/data-sources-download.pdf
- https://api.usaspending.gov/
- https://api.usaspending.gov/docs/endpoints
- https://github.com/fedspendingtransparency/usaspending-api/blob/master/usaspending_api/api_contracts/contracts/v2/transactions.md
- https://github.com/fedspendingtransparency/usaspending-api/blob/master/usaspending_api/api_contracts/search_filters.md

Using `action_date`, a fixed submission lag, current `last_modified_date`, or the current API row as event availability would mix materially different lags and permit corrected data to leak backward. The 90-day defense delay alone invalidates a uniform lag rule. Because point-in-time public state fails first, the proposed new positive-obligation definitive-contract family was not counted and recipient-name coverage was not measured.

Final state: `public_availability_gate_passed=false`, `historical_version_gate_passed=false`, `preregistered=false`, `transaction_index_acquired=false`, `event_family_counted=false`, `recipient_mapping_performed=false`, `event_cube_opened=false`, `cells_completed=0`, `post_publication_outcomes_loaded=false`. Do not reopen using action date, assumed submission/pipeline lags, current API/bulk rows, UEI or DUNS parent inference, products, agencies, subsidiaries, parents, former names, abbreviations, fuzzy matches, or manual aliases; do not mix grants, loans, IDV ceilings, subawards, modifications, deobligations, or agency announcements. No development or consumed period, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.
