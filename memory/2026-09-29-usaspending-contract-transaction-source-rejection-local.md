# Local fallback memory: USAspending contract transactions

summary: USAspending 2021-2023 federal contract transactions were rejected at the public-availability and historical-version gates. Official documentation shows action date precedes FPDS submission and USAspending publication, with ordinary multi-day reporting/pipeline lags and a 90-day DOD/USACE delay. Current API rows expose action and last-modified dates but not each transaction's first-publication timestamp or immutable first-public version; current correction/delete state cannot reconstruct all historical public states. No transaction corpus was acquired, no event family was counted, no recipient mapping was performed, the event cube was not opened, no outcome was read, and cells_completed is zero.

stage: source-public-availability-gate

kpi_version: versionless-usaspending-contract-source-screen

tags: project:quant-agent-team, market:cn_a, freq:daily, stage:source-public-availability-gate, strategy:usaspending-contract-award, status:rejected, source:usaspending, sample:coverage-limited-527

next_step: Audit U.S. Department of Defense 2021-2023 daily Contracts announcements as a genuinely different official publication family. First prove release timestamp semantics, complete archive pagination, stable release identity, historical page or attachment bytes, and correction/update/retraction chains. Predefine one economically homogeneous new definitive contract-award announcement family and do not mix options, modifications, task orders under existing vehicles, grants, cooperative agreements, indefinite-delivery ceilings, or procurement forecasts for volume. Before any outcome read, count official releases and evaluate coverage using only the named prime contractor's complete legal entity name mechanically identical to a frozen SEC issuer. Prohibit project/product names, place of performance, subcontractors, subsidiaries, parents, former names, abbreviations, fuzzy matches, and manual aliases. Freeze and switch if public timing, versioning, event semantics, volume, or exact-name coverage cannot be proven.

## Frozen evidence

USAspending nightly/current-state access does not preserve an auditable first-public transaction state, and contract publication lag varies materially, including a 90-day DOD/USACE delay. `ABANDON_USASPENDING_CONTRACT_PUBLICATION_HISTORY_GATE`; `transaction_index_acquired=false`; `recipient_mapping_performed=false`; `cells_completed=0`; `post_publication_outcomes_loaded=false`. MCP memory search/create remained unavailable, so this tagged local fallback needs later backfill.
