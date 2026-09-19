---
type: data-decision
summary: Official Treasury auction XML has an auction date, release time and bid-to-cover field, but the fixed sample cannot support the examined pre-release 60-pair TLT duration-beta stock map across all three training years; no auction line was preregistered or return-ranked.
stage: source-design-screen
kpi_version: treasury-auction-design-v0
tags:
  - project:quant-agent-team
  - market:cn_a
  - freq:daily
  - stage:source-design-screen
  - strategy:treasury-auction-design-v0
  - status:rejected-mapping
next_step: Seek a genuinely different official point-in-time source with a causal stock mapping and sufficient frozen-sample training coverage; preserve this design-screen evidence.
---

Frozen 527-symbol 2021–2023 sample is coverage-limited, not full market. TLT has 65/129/163 finite bar-5 dates in 2021/2022/2023. Under a 60 strictly prior paired TLT/stock proxy, an optimistic all-session upper bound has zero 2021 sessions with 150 eligible symbols, 58 in 2022, 250 in 2023; the first such session is 2022-10-10. No auction values, stock post-release outcomes, or grid cells were used. The official Treasury XML's `ReleaseTime` supports further source research, but no parameter relaxation was adopted. MCP memory search/create unavailable; this tagged local fallback needs later MCP backfill.
