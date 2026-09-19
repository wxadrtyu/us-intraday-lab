# DOL weekly UI claims: source gate rejection

The fixed 527-symbol 2021–2023 training sample is **coverage-limited, not full market**. All 156 exact official archive-linked PDFs were captured (52 per year), and every local raw PDF matches its SHA-256 in the frozen manifest. The PDF manifest SHA-256 is `1a38d3a4d6ee868f1bb3ebf020f51508bfb01740441018e341bb228082cb4204`; the prior source inventory SHA-256 is `fd2f0da47c5fce9c3b4991ab1c37ea7ed156ad7fdf81fb6494ba6b8c69c9fb8b`.

The preregistered **first-page-only** extraction succeeded on 153/156 releases. On 2022-04-14 and 2022-10-06, PDF text extraction splits the initial-claims advance label (`a dvance` / `adv ance`), so its exact phrase is absent after mechanical whitespace normalization. On 2023-04-06, page one is a seasonal-adjustment methodology notice with neither first-published advance measure. The dates and PDF hashes are preserved; no later page, revised table, alternate parser heuristic, or inferred value was substituted.

The required 156/156 source-schema gate therefore failed: `ABANDON_DOL_UI_CLAIMS_COVERAGE_GATE`. Zero of the 400 frozen return cells were run, and no post-availability outcomes were loaded. Do not re-open or locally tune this family. The next research hypothesis must use a genuinely different free, auditable point-in-time source; no Paper, broker or pool action is implied.
