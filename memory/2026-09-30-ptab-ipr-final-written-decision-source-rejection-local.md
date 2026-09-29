# Local fallback memory: PTAB IPR final written decisions

summary: PTAB 2021-2023 inter partes review final written decisions were rejected at the historical-version gate. Official P-TACTS and Open Data Portal facilities expose current public cases, decision metadata, stable-looking document identifiers, current PDFs, and last-modified timestamps, but USPTO expressly permits mistakenly filed documents to be deleted by contacting PTAB. The official current API has no original-file hashes, deletion timestamps, superseded-byte archive, or complete amendment/correction/replacement manifest. Current state therefore cannot prove the bytes and metadata public at historical decision entry. No decision corpus was acquired, no homogeneous unpatentable-claim family was counted, no patent-owner mapping was performed, the event cube was not opened, no outcome was read, and cells_completed is zero.

stage: source-history-gate

kpi_version: versionless-ptab-ipr-fwd-source-screen

tags: project:quant-agent-team, market:cn_a, freq:daily, stage:source-history-gate, strategy:ptab-ipr-final-written-decision, status:rejected, source:uspto-ptab, sample:coverage-limited-527

next_step: Audit Federal Register 2021-2023 FDA final orders withdrawing approval of abbreviated new drug applications as a genuinely different statutory publication family. First prove Federal Register publication date, document number, and GovInfo PDF identity; complete official query reproduction; correction or republication links; and one economically homogeneous final withdrawal-order family, without mixing proposed withdrawals, NDA withdrawals, biologics, safety communications, shortages, enforcement, or approval actions. Before any outcome read, count official metadata and evaluate coverage using only each named ANDA applicant's complete legal entity name mechanically identical to a frozen SEC issuer. Do not split product rows into pseudo-events or map drug names, labels, application numbers, manufacturers other than the named applicant, subsidiaries, parents, former names, abbreviations, fuzzy matches, or manual aliases. Freeze and switch if public timing, document versioning, event semantics, volume, or exact-name coverage cannot be proven.

## Frozen evidence

USPTO's current PTAB systems expose current documents and last-modified metadata while permitting deletion of mistaken filings and publishing no complete historical-byte/version ledger. `ABANDON_PTAB_IPR_FWD_HISTORY_GATE`; `decision_corpus_acquired=false`; `patent_owner_mapping_performed=false`; `cells_completed=0`; `post_publication_outcomes_loaded=false`. MCP memory search/create remained unavailable, so this tagged local fallback needs later backfill.
