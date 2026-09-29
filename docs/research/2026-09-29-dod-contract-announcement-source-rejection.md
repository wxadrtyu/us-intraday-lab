# Department of Defense daily Contracts announcement source rejection

Decision: **ABANDON_DOD_CONTRACT_ANNOUNCEMENT_HISTORY_GATE**. The proposed 2021-2023 Department of Defense daily Contracts announcement line is frozen at the historical-version gate, before archive acquisition, event-family counting, prime-contractor matching, event-cube access, or any post-publication return read. The frozen event cube remains a **527-symbol coverage-limited sample, not the full US market**.

## Official source audit

Defense.gov assigns daily Contracts pages stable-looking Article identifiers and displays a release date in each title. Examples include the official pages for February 28, 2022, August 1, 2022, May 2, 2023, and July 28, 2023. This is sufficient to identify the current official page, but not to prove the bytes or constituent awards that were public at the displayed date and time.

The current May 2, 2023 page contains an explicit `UPDATE` adding a Signature Flight Support award made on March 6, 2023. The added item is now embedded in the page carrying the May 2 release identity. The current page does not expose an immutable original object, original-content hash, edit timestamp, version manifest, or complete correction/update/retraction ledger. Defense.gov also labels these pages as part of a historical collection whose information or links may be outdated. Consequently, hashing the current page would authenticate only the current edited representation; it cannot authenticate the first-public state or assign later-added content to the displayed release date.

Official sources:

- https://www.defense.gov/News/Contracts/
- https://www.defense.gov/News/Contracts/Contract/Article/2949169/
- https://www.defense.gov/News/Contracts/Contract/Article/3112446/
- https://www.defense.gov/News/Contracts/Contract/Article/3382083/
- https://www.defense.gov/News/Contracts/Article/3475675/

The daily pages also combine economically different actions: new awards, modifications, exercised options, delivery or task orders under existing vehicles, and indefinite-delivery ceilings. A homogeneous new definitive-contract award family could only be filtered from page content after point-in-time content was proven. Because historical public state fails first, no archive was persisted, no page or award count was used, and no issuer-name coverage diagnostic was run.

Final state: `public_release_identity_exists=true`, `historical_version_gate_passed=false`, `preregistered=false`, `archive_corpus_acquired=false`, `event_family_counted=false`, `prime_contractor_mapping_performed=false`, `event_cube_opened=false`, `cells_completed=0`, `post_publication_outcomes_loaded=false`. Do not reopen using current page bytes, the displayed page date, inferred publication time, current HTTP headers, or later `UPDATE` content as original state. Do not mix options, modifications, task or delivery orders, existing-vehicle awards, grants, cooperative agreements, indefinite-delivery ceilings, forecasts, products, projects, places of performance, subcontractors, subsidiaries, parents, former names, abbreviations, fuzzy matches, or manual aliases. No development or consumed period, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.
