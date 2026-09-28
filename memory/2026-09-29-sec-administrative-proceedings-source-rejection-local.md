---
type: failed-experiment
summary: SEC Administrative Proceedings/Orders Instituting Proceedings failed the preregistration source gate. SEC states its administrative-proceeding lists may be incomplete, not all filings are online, and online filings are generally posted within five business days, so printed release date cannot be assumed to be first web availability. Current official PDFs for releases 34-97497 and 34-97498 preserve the May 12, 2023 release date and number while identifying themselves as corrected and carrying May 18 HTTP modification times; no original-byte or correction-time ledger is available. No full inventory, mapping, event cube, or outcomes were opened.
stage: source-gate
kpi_version: sec-administrative-proceedings-v1
tags:
  - project:quant-agent-team
  - market:cn_a
  - freq:daily
  - market:us
  - freq:5min
  - stage:source-gate
  - strategy:sec-administrative-proceedings
  - status:rejected
next_step: Preserve the official-page and corrected-PDF hashes. Do not infer posting time from printed release date or current Last-Modified, and do not drop corrected matters after seeing them. Audit a genuinely different free official dated-document family with explicit public availability and recoverable first-version bytes before any preregistration or outcome access.
---

Decision is `ABANDON_SEC_ADMINISTRATIVE_PROCEEDINGS_SOURCE`; `source_point_in_time=false`, `preregistered=false`, `full_index_acquired=false`, `pdf_inventory_acquired=false`, `issuer_mapping_performed=false`, `event_cube_opened=false`, `cells_completed=0`, and `post_availability_outcomes_loaded=false`.

External source-audit manifest SHA-256 is `bf14cc3c35b1b2fc025ce4322ece0a5a2b582ea6040637e979c2a02fe56846ab`. The 527-symbol 2021-2023 sample remains coverage-limited, not full market. MCP memory search/create remain unavailable, so this tagged local fallback needs later backfill.
