# Local fallback memory: EPA pesticide cancellation orders

summary: The Federal Register EPA pesticide final cancellation-order family was rejected at the source-volume/design gate. The official 2021-2023 API term query returned 74 broad search results; an intentionally overinclusive title upper bound containing Cancellation Order had only 35 documents with 15/10/10 per year. The predeclared generic final product-registration cancellation-order family had only 12 documents with 6/3/3 per year, far below the fixed 100-total and 20-per-year source floors. No response or PDF corpus was persisted, no registrant mapping was performed, the event cube was not opened, no outcome was read, and cells_completed is zero.

stage: source-volume-gate

kpi_version: versionless-epa-pesticide-cancellation-order-source-screen

tags: project:quant-agent-team, market:cn_a, freq:daily, stage:source-volume-gate, strategy:epa-pesticide-cancellation-order, status:rejected, source:federal-register, sample:coverage-limited-527

next_step: Audit FINRA official 2021-2023 Reg SHO daily short-sale volume files as a genuinely different exchange-microstructure source. First prove the official archive is complete, each file has a defensible public availability time, original daily bytes are stable or versioned, corrections and replacements are auditable, and event-time symbols can be matched mechanically to the frozen point-in-time sample. Before any outcome read, predefine one causal and economically homogeneous short-volume event construction without inspecting returns, and keep exchange-reporting facilities separate rather than pooling after observation. Do not infer symbol histories, fold share classes, or use issuers, parents, subsidiaries, brands, former names, fuzzy matches, or manual aliases. Freeze and switch if availability, historical identity, construction, event volume, or coverage cannot be proven.

## Frozen evidence

The broad official title upper bound was 35 documents with 15/10/10 per year; the generic final product-registration cancellation-order family was 12 with 6/3/3. Table rows are not separate public-release events. `ABANDON_EPA_PESTICIDE_CANCELLATION_ORDER_VOLUME_GATE`; `source_volume_gate_passed=false`; `registrant_mapping_performed=false`; `cells_completed=0`; `post_publication_outcomes_loaded=false`. MCP memory search/create remained unavailable, so this tagged local fallback needs later backfill.
