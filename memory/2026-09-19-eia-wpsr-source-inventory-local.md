# EIA WPSR official source inventory checkpoint

- summary: Sequential official EIA WPSR archive acquisition froze the raw index and 154 unique 2021-2023 issue pages with 154 exact linked Table 4 URLs before any training CSV or outcome load. Counts were 52/51/51 by year; all page hashes matched the external source manifest. Source manifest SHA-256 is 7d64803e26acd2ea1e2db1c05c466280155e30d7a235e9220528bd22ba6b9690. The 527-symbol research sample is coverage-limited, not full market.
- stage: source-inventory-frozen
- kpi_version: none; versionless training feasibility
- type: data-decision
- tags: project:quant-agent-team, market:cn_a, freq:daily, strategy:eia-wpsr-supply-shock, status:source-manifest-complete
- validation: 154 unique release dates and CSV URLs; 154/154 raw page SHA-256 matches; index SHA-256 match; source process exit code 0. No Table 4 training CSV or return cell run.
- next_step: Use the new frozen-manifest-only CSV fetch path, verify all raw CSV hashes/schema, then assess preregistered feature and family coverage before any post-availability returns.
