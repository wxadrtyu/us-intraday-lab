# DOL weekly UI-claims labor-shock preregistration

- summary: Preregistered a versionless, training-only DOL weekly claims release screen on the frozen 2021-2023 527-symbol coverage-limited sample, not full market. Source is three official year-index responses and their exact 156 release-specific PDFs; first page must carry a date-matched 8:30 ET embargo and unambiguous first-published SA initial/insured claims. Availability begins the first sample session strictly after publication. SPY bar-5 beta uses exactly 60 paired observations strictly before publication, with no sign filter or missing-as-zero. Five families are initial and insured improvement/deterioration plus concordant deterioration, using deviations from prior-12-release medians. All source/coverage/cost/delay and 400-cell hard gates are frozen before any training PDF acquisition.
- stage: design-preregistration
- kpi_version: none; versionless training feasibility
- type: strategy-hypothesis; data-decision
- tags: project:quant-agent-team, market:cn_a, freq:daily, strategy:dol-ui-claims, status:preregistered
- coverage_gate: Exactly 52 source PDFs in each training year with all hashes/first pages valid; 200 unique SPY-beta-eligible symbols, 150 on 100 availability sessions, 20,000 symbol-release pairs; five families each 30 releases overall and five per year. Failure means zero outcome cells and no tuning.
- diagnostic: Five families x five decision bars x four holds x four top counts = 400, 9/18 bp and one-bar delay, 40 signal sessions and 10/year, >=20% annualized net, IR>=0.8, maxDD<20%, two positive years, stress/delay annualized positive; at least two retained families only suggests development-data acquisition.
- next_step: Implement official year-index inventory/hash capture test-first and commit before fetching 2021-2023 PDFs. Preserve all missingness and keep Paper/broker/pool/shutdown forbidden.
