# PTAB IPR final-written-decision source rejection

Decision: **ABANDON_PTAB_IPR_FWD_HISTORY_GATE**. The proposed 2021-2023 Patent Trial and Appeal Board inter partes review final-written-decision line is frozen at the historical-version gate, before decision-corpus acquisition, outcome-family counting, patent-owner matching, event-cube access, or any post-publication return read. It remains strictly separate from the previously frozen USPTO patent-grant line. The frozen event cube remains a **527-symbol coverage-limited sample, not the full US market**.

## Official source audit

USPTO states that all public AIA review cases and associated public documents can be searched in P-TACTS without registration. The official Open Data Portal decision API says public PTAB trial decisions are available from September 2012 and exposes trial number, decision issue date, document filing date, document identifier, document number, file URI, document size, current last-modified timestamps, outcome category, and patent-owner real-party-in-interest name. Those fields give the current record stable-looking identifiers and useful metadata.

They do not establish an immutable first-public state. USPTO's P-TACTS FAQ expressly says a mistakenly filed document can be deleted by contacting PTAB AIA Trials. The current API exposes `lastModifiedDateTime` and current document metadata, but the official API documentation provides no historical component manifest, original-file hash, deletion timestamp, superseded-byte archive, or complete amendment/correction/replacement ledger. Final written decisions also remain subject to rehearing or Director Review through separately filed docket papers. A current document identifier or current PDF hash therefore cannot prove that the same bytes and metadata were the complete public record at the historical decision-entry time.

Official sources:

- https://www.uspto.gov/patents/ptab/about-p-tacts
- https://www.uspto.gov/patents/ptab/faqs
- https://www.uspto.gov/sites/default/files/documents/p-tacts_faqs_20221007.pdf
- https://data.uspto.gov/apis/ptab-trials/search-decisions
- https://data.uspto.gov/apis/ptab-trials/download-decisions
- https://www.uspto.gov/patents/ptab/decisions/director-review-process

The Open Data Portal now requires account/API-key access, while P-TACTS warns against bulk use. More importantly, authenticated access to the current corpus would not repair the missing history. Because the historical-version gate fails first, the proposed homogeneous subset of IPR final written decisions finding at least one challenged claim unpatentable was not counted and patent-owner coverage was not measured.

Final state: `current_public_index_exists=true`, `public_timing_semantics_proven=false`, `historical_version_gate_passed=false`, `preregistered=false`, `decision_corpus_acquired=false`, `event_family_counted=false`, `patent_owner_mapping_performed=false`, `event_cube_opened=false`, `cells_completed=0`, `post_publication_outcomes_loaded=false`. Do not reopen using current API/P-TACTS rows, current PDFs or hashes, `decisionIssueDate`, `documentFilingDate`, current `lastModifiedDateTime`, or an assumed docket-entry lag. Do not mix institution decisions, settlements, terminations, rehearing decisions, Director Review, PGR, CBM, appeals, petitioners, patents, products, inventors, subsidiaries, parents, former names, abbreviations, fuzzy matches, or manual aliases. No development or consumed period, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.
