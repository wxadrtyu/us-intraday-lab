# Local fallback memory: USCG Port State Control detentions

summary: USCG Port State Control detentions were rejected at the issuer-entity structure gate. Official annual reports and the List of Ships Detained provide vessel name, IMO number, detention date, ship type, port, flag, recognized organization fields, deficiency summary, and case status, but not the full case-level owner or operator legal entity required for exact matching to a frozen SEC issuer. Resolving a vessel or IMO number would require time-varying external registry links through registered owners, managers, charterers, subsidiaries, or parents, all forbidden by the frozen contract. The 2023 annual report had 101 detentions, so raw count does not repair the absent legal entity. No detention files were acquired, no homogeneous ground was counted, no mapping was performed, the event cube was not opened, no post-availability outcome was read, and cells_completed is zero.
stage: source_entity_structure_gate
kpi_version: frozen_event_cube_2021_2023_527_coverage_limited
memory_type: failed-experiment
tags:
  - project:quant-agent-team
  - market:cn_a
  - freq:daily
  - stage:source_entity_structure_gate
  - strategy:uscg_port_state_detentions
  - status:rejected
next_step: Audit FDA 2021-2023 weekly Enforcement Reports for one predeclared homogeneous Class I medical-device recall family. First prove weekly report publication timing, archive completeness, stable recall numbers, product-type and classification semantics, update or termination chains, immutable historical releases, and first-publication bytes. Then assess exact recalling-firm legal-name matches to frozen SEC issuers. Do not infer issuers from product or trade names, manufacturers not named as recalling firms, subsidiaries, parents, brands, addresses, or aliases, and do not read outcomes before a frozen coverage gate passes.
