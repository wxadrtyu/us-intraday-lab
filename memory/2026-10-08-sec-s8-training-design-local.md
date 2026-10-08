# Local fallback memory: SEC original Form S-8 training design

summary: The user approved option A for the exact original SEC Form S-8 line: a three-session event life and five frozen families (all-event continuation, all-event reversal, complete-lookback 252-session first/renewal continuation, 252-session repeat continuation, and 63-session clustered-repeat reversal). The design fixes causal next-session availability, metadata-only repetition labels, joint within-clock ranking, a 5 x 5 x 4 x 4 = 400-cell grid, 9/18 bp costs, one-bar delayed entry, and the existing training retention gates. Primary-document bodies and all post-acceptance outcomes remain unopened.

stage: sec-s8-training-design

kpi_version: versionless-training-feasibility

tags: project:quant-agent-team, market:cn_a, freq:daily, stage:training-design, strategy:sec-original-s8, status:awaiting-written-spec-review

next_step: Obtain user review of the committed written specification. After explicit approval, invoke the writing-plans workflow and create a tested implementation plan. Only after that plan is approved may implementation sequentially read the frozen 2021-2023 training outcomes. Do not load development or consumed periods, create a strategy version, activate Paper, mutate a monitoring pool, call broker/submit/cancel paths, route orders, or shut down anything.

Frozen state: `event_life_sessions=3`; `families=5`; `decision_bars=2/5/11/17/23`; `holding_bars=1/2/4/6`; `top_counts=1/3/5/10`; `cells=400`; `standard_cost_bp=9`; `stress_cost_bp=18`; `delay_bars=1`; `minimum_signal_sessions=120`; `minimum_annualized_return=0.20`; `minimum_information_ratio=0.80`; `maximum_drawdown_strictly_below=0.20`; `minimum_positive_calendar_years=2`; `minimum_retained_families=2`; `coverage_pairs=482`; `coverage_issuers=258`; `coverage_artifact_sha256=62943eb65d564e07960efcd206563adf1baebd5715d0c2db30a56cbe15be2ca8`; `event_cube_outcomes_opened=false`; `cells_completed=0`; `primary_document_bodies_opened=false`. MCP memory search/create was unavailable, so this tagged local fallback requires later backfill.
