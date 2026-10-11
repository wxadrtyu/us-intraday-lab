# Local fallback memory: daily price-state multi-factor design

- type: `strategy-hypothesis`
- summary: Preregistered a genuinely distinct sparse daily price-state family using completed-bar candlestick geometry, range compression, volume shocks, capitulation, and failed-breakdown states. The fixed grid contains 400 cells with 9/18 bp and one-bar-delay stresses.
- stage: `design-frozen`
- kpi_version: `daily-price-state-multifactor-training-v1`
- tags:
  - `project:quant-agent-team`
  - `market:cn_a`
  - `freq:daily`
  - `stage:design-frozen`
  - `strategy:daily-price-state-multifactor-v1`
  - `status:preregistered`
- next_step: Implement under TDD, freeze a code-only checkpoint, and then read only the frozen 2021-2023 training outcomes exactly once.
