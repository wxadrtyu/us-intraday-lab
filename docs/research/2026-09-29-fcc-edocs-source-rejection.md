# FCC Daily Digest / EDOCS enforcement-order source rejection

## Decision

Freeze this line as `ABANDON_FCC_EDOCS_REPRODUCIBILITY_GATE`. FCC release semantics and the EDOCS correction model are promising, but the official historical index could not be reproduced from the current public interfaces. No event-family preregistration, issuer mapping, or outcome access is permitted without a complete official inventory.

This decision applies only to the frozen 2021-2023 sample of 527 symbols. That sample is coverage-limited and is not the full US equity market.

## Official semantics that passed

- FCC describes the Daily Digest as its routine public listing of documents released by the agency. An official Commission order explains that delegated-authority actions generally take effect upon release and distinguishes the document's release date from its later appearance in the Daily Digest.
- FCC's official 2003 EDOCS improvement notice says the system supports DA/FCC number, docket, date-range, title, description, and other indexed searches, provides full indexing records, and links errata to original documents.
- Official attachment URLs use stable FCC/DA document numbers and attachment identifiers. Current PDFs expose adopted and released dates and later errata are separately numbered documents that state which released document they amend.

These facts would support a conservative availability rule based on a provable release/publication record, with linked errata treated as later events rather than silently rewriting the original event.

## Decisive reproducibility failure

The official EDOCS RSS API returned HTTP 504 for both the combined feed and the `Order` document-type feed during this audit. The official EDOCS web search returned HTTP 403. The static `docs.fcc.gov` attachment host remained reachable, but it is an object store, not a complete 2021-2023 searchable inventory with pagination, release metadata, document type, bureau, and erratum relationships.

Without a reproducible official index, the audit cannot enumerate the full 2021-2023 universe, prove pagination completeness, select one economically homogeneous NAL/Forfeiture Order or license denial/revocation family before coverage, measure event volume, or audit every original-to-erratum link. Search-engine results, guessed FCC/DA numbers, current headline pages, and hand-collected attachments are inadmissible substitutes because they introduce unknown omissions and observation-driven selection.

This is a source-access/completeness rejection, not evidence that FCC documents lack legal relevance. The line may be reconsidered only as a new preregistration if an official full historical EDOCS export or reproducible official API becomes available; the current failed endpoint observations cannot be patched with third-party indexes.

## Frozen consequences

- Do not scrape search-engine indexes, enumerate guessed attachment numbers, mix Daily Digest entries with headline pages, or use third-party EDOCS mirrors to fill the official inventory.
- Do not combine NALs, forfeiture orders, consent decrees, license denials, revocations, assignment decisions, public notices, and unrelated adjudicatory orders to manufacture volume.
- Do not map licensees, call signs, stations, brands, subsidiaries, parents, former names, abbreviations, fuzzy names, or hand-built aliases to listed issuers.
- Do not load post-release outcomes or run any fixed-grid cell.

Final state: `source_index_reproducible=false`, `preregistered=false`, `full_index_acquired=false`, `pdf_inventory_acquired=false`, `issuer_mapping_performed=false`, `event_cube_opened=false`, `cells_completed=0`, `post_availability_outcomes_loaded=false`. No development or consumed period, strategy version, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.
