# Local fallback memory: NHTSA ODI investigation openings

summary: NHTSA ODI formal investigation openings were rejected at the source-volume/design gate. The official DOT Socrata index has 104 total 2021-2023 investigations across all types, but the only predeclared homogeneous families are too small: Preliminary Evaluations total 59 with 23/13/23 per year, and Engineering Analyses total 8 with 3/2/3. Pooling PE and EA or adding AQ, RQ, DP, EQ, closing resumes, recalls, TSBs, or complaints is forbidden. No documents were acquired, no issuer mapping was performed, the event cube was not opened, no outcome was read, and cells_completed is zero.

stage: source-volume-gate

kpi_version: versionless-nhtsa-odi-opening-source-screen

tags: project:quant-agent-team, market:cn_a, freq:daily, stage:source-volume-gate, strategy:nhtsa-odi-opening, status:rejected, source:nhtsa-odi, sample:coverage-limited-527

next_step: Audit official Nasdaq Trader 2021-2023 single-stock LULD trading-pause notices as a genuinely different exchange event family. First prove the historical archive is complete, timestamps are public-release times, notice and pause identifiers are stable, cancellations/corrections/resumptions are linked, and original records or immutable daily files are retained. Predeclare only one pause reason and do not mix regulatory halts, news pending, exchange operational halts, resumptions, delistings, or corporate actions. Use only the official symbol shown at the event time for a mechanical point-in-time match to the frozen sample; do not infer former/current symbols, share classes, parents, subsidiaries, brands, or aliases. Do not read outcomes before a frozen metadata-only coverage gate passes.

## Frozen evidence

The official Socrata filter on `open_date` from 2021-01-01 through 2023-12-31 returned 104 distinct action rows. Preliminary Evaluation had 59 actions (23/13/23) and 27 displayed manufacturers; Engineering Analysis had 8 actions (3/2/3) and 6 displayed manufacturers. Both fail the fixed 100-total and 20-per-year high-frequency source floors before any legal-name overlap is examined. `ABANDON_NHTSA_ODI_OPENING_VOLUME_GATE`; `cells_completed=0`; `post_availability_outcomes_loaded=false`. MCP memory search/create remained unavailable, so this tagged local fallback needs later backfill.
