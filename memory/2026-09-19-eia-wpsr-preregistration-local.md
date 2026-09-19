# EIA WPSR physical-inventory training preregistration

- summary: The frozen 2021-2023 event cube defines 527 symbols, a coverage-limited sample rather than the full market. Preregistered a distinct EIA dated-issue Table 4 inventory-change innovation hypothesis with strictly next-session availability, historical bar-5 XLE beta exposure, four exact inventory rows plus one concordance family, a source/feature coverage gate, and a 400-cell cost/delay training diagnostic. This records a design, not a passed candidate or completed acquisition.
- stage: design-preregistration
- kpi_version: none; versionless training feasibility
- type: strategy-hypothesis; data-decision
- tags: project:quant-agent-team, market:cn_a, freq:daily, strategy:eia-wpsr-supply-shock, status:preregistered
- source: Official EIA WPSR previous-issues archive, release-specific issue pages and their exact linked Table 4 CSVs. Freeze raw bytes, URLs, retrieval metadata and SHA-256 before outcome analysis; reject gaps and changed hashes.
- causal_boundary: First frozen sample session strictly after each published release date; 60 prior paired bar-5 symbol/XLE sessions for exposure; 12 prior complete EIA releases for inventory-change median; no later-period ranking, execution or pool mutation.
- coverage_gate: At least 48 releases/year and 150 total; at least 150 beta-eligible non-XLE symbols on 100 release sessions and 20,000 symbol-release pairs; at least 40 active releases/family and 10/family/year. Fail before post-availability returns.
- diagnostic: Five families x five decision bars x four holding bars x four top counts = 400; 9/18 bp and one-bar delay; at least two passing families only suggests development-data acquisition.
- next_step: Implement source manifest parser test-first, commit it before sequential 2021-2023 Table 4 download; retain missingness and freeze any coverage failure without tuning.
