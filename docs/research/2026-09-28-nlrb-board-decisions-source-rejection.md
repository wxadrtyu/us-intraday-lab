# NLRB Board Decisions source rejection

Decision: **ABANDON_NLRB_BOARD_DECISIONS_SOURCE**. This line is frozen during preregistration design, before URL/PDF inventory acquisition, issuer mapping, event-cube access, or any post-issuance return read. The frozen 2021–2023 event cube remains a **527-symbol coverage-limited sample, not the full US market**.

## Official-source audit

The [NLRB Board Decisions index](https://www.nlrb.gov/cases-decisions/decisions/board-decisions) exposes an `Issuance Date`, citation, case name, case number, and an NLRB document link. The agency's [2023 Guide to Board Procedures](https://www.nlrb.gov/sites/default/files/attachments/pages/node-174/guide-to-board-procedures-2023.pdf) says that for E-Service recipients, service of the decision is the date the Board sends the email notification that the decision issued. Those statements can support a conservative first-sample-session-after-issuance availability rule.

Gross event volume is not the immediate blocker. Official Performance and Accountability Reports say that the Board issued 243 contested-case decisions in FY2021, 243 in FY2022, and 246 in FY2023, or 732 across the three fiscal years before any exact-issuer restriction. This is only a design-stage workload count, not a calendar-year URL inventory or coverage result.

## Point-in-time failure

The same official Board Decisions index explicitly states: **“Slip opinions are subject to revision before publication in bound volumes.”** The live index points to the currently linked NLRB document object but exposes no revision timestamp, revision ledger, original-object identifier, or historical byte inventory for each issuance-date row. A current PDF hash would freeze only the current slip opinion. It would not prove that those bytes, caption, disposition, or text were the version publicly available on the 2021–2023 issuance date.

Later bound volumes do not solve the problem. They are the post-revision publication state and cannot be treated as if available on the earlier slip-opinion issuance date. Weekly summaries are expressly informational and not substitutes for Board opinions; they also do not provide a complete byte-version history for every decision.

Because the event definition depends on the official decision and caption at first public issuance, the source cannot satisfy the required historical point-in-time content contract. No current PDF, inferred revision lag, weekly-summary text, or later bound-volume text may be backdated to issuance. The design is rejected without testing exact caption-to-issuer coverage.

Final state: `preregistered=false`, `pdf_inventory_acquired=false`, `issuer_mapping_performed=false`, `event_cube_opened=false`, `cells_completed=0`, `post_availability_outcomes_loaded=false`. No development or consumed period, strategy version, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.
