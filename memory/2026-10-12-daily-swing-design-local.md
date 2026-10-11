# Local fallback memory: daily swing multi-factor design

- type: `strategy-hypothesis`
- summary: Frozen a 400-cell multi-day technical allocation design using five daily factor composites, four signal lags, four cohort holding periods, and five top counts. Returns are open-to-next-open with explicit overlapping-cohort weights, turnover, cash, costs, and missing-open rejection.
- stage: `design-frozen`
- kpi_version: `daily-swing-multifactor-training-v1`
- tags:
  - `project:quant-agent-team`
  - `market:cn_a`
  - `freq:daily`
  - `stage:design-frozen`
  - `strategy:daily-swing-multifactor-v1`
  - `status:preregistered`
- next_step: Implement under TDD, push a code-only checkpoint, then read only frozen 2021-2023 training outcomes.
