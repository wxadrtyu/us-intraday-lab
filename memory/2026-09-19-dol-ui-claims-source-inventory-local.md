# DOL weekly claims source inventory frozen

- summary: Captured official 2021/2022/2023 DOL OUI annual news-release indexes sequentially and froze 52 exact PDF links in each year, 156 unique release dates total, before fetching any training PDF. All three raw year-index SHA-256 hashes matched the external immutable manifest. Source manifest SHA-256 is fd2f0da47c5fce9c3b4991ab1c37ea7ed156ad7fdf81fb6494ba6b8c69c9fb8b. The 527-symbol training sample is coverage-limited, not full market.
- stage: source-inventory-frozen
- kpi_version: none; versionless training feasibility
- type: data-decision
- tags: project:quant-agent-team, market:cn_a, freq:daily, strategy:dol-ui-claims, status:source-manifest-complete
- validation: 52/52/52 official links, 156 unique dates/URLs, 3/3 raw HTML SHA-256 checks, source process exit code 0; zero PDFs and zero return cells at checkpoint.
- next_step: Sequentially retrieve only the 156 exact frozen official PDFs with raw SHA-256 and missingness retained; then test first-page PDF extraction before any outcome or coverage verdict.
