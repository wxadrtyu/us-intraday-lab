# FDA human-drug PTE review-period entity-structure rejection

Decision: **ABANDON_FDA_HUMAN_DRUG_PTE_ENTITY_GATE**. The preregistered 2021-2023 Federal Register family of FDA human-drug patent-term-extension regulatory-review-period determinations is frozen at the applicant-entity structure gate. All 103 official GovInfo PDFs were acquired and hash-frozen, but the notices do not identify the legal entity that filed the patent-term-extension application. No issuer mapping, event-cube outcome access, or training cell followed. The frozen sample remains a **527-symbol coverage-limited sample, not the full US market**.

## Frozen official corpus

The exact preregistered metadata response remains 406,578 bytes with SHA-256 `a1c787cb19f47a9ab1037de56618559235897b772c6280df810e98361925e887`. The 103 retained GovInfo PDFs were downloaded sequentially from their frozen `pdf_url` values:

- 103 successful PDF payloads and zero missing or non-PDF objects;
- 22,104,470 total bytes;
- 103 distinct SHA-256 values;
- PDF manifest 50,952 bytes, SHA-256 `477810956ff9025561c13a7575b44b560d6db41422fd64d65cc3b530bb71727e`.

All 103 target notice sections were text-extracted from the official PDFs. The notices identify the product, NDA dates, regulatory-review-period components, the extension days sought, and refer generically to `the applicant`, `this applicant`, or `the applicant for extension`. Across the complete corpus, zero target sections contain a named-entity construction equivalent to `applicant for extension is ...`, `patent-term-extension applicant: ...`, or `application ... filed/submitted by ...`.

The absent role cannot be replaced by the marketing applicant, NDA holder, product sponsor, patent owner, assignee, agent, product name, patent number, application number, or an external USPTO patent-extension file. Those can be different legal persons, and joining them would violate the preregistered rule requiring the complete entity expressly identified in the same official PDF as the patent-term-extension applicant. The document corpus therefore cannot support the required mechanical one-to-one issuer exposure.

Final state: `source_complete=true`, `training_pdf_inventory_acquired=true`, `pdf_document_count=103`, `pdf_unique_hashes=103`, `target_sections_extracted=103`, `explicit_named_pte_applicants=0`, `entity_structure_gate_passed=false`, `frozen_527_mapping_performed=false`, `event_cube_opened=false`, `cells_completed=0`, `post_publication_outcomes_loaded=false`. Do not reopen by using products, NDA holders, marketing applicants, sponsors, patent owners, assignees, agents, patents, external docket joins, subsidiaries, parents, affiliates, former names, abbreviations, fuzzy matches, or manual aliases. The filters, role rule, and coverage thresholds remain frozen. No development or consumed period, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.
