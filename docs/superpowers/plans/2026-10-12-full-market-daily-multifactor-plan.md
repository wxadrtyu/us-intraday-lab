# Full-market daily technical multifactor implementation plan

1. Add contract tests for the immutable daily source and monthly point-in-time
   universe hashes, exact 400-cell grid, forbidden inputs, and consumed-period
   labeling.
2. Implement a read-only daily panel loader that joins eligibility by effective
   calendar month and fails closed on duplicate keys, out-of-month membership,
   or missing selected entry/exit bars.
3. Implement the five causal feature families with completed-bar lags and
   deterministic cross-sectional ranks; verify every feature against small
   hand-computed fixtures.
4. Implement equal-weight overlapping cohorts with 9 bp, 18 bp, and one-session
   delayed-entry scenarios sharing the same signal and validity mask.
5. Add atomic checkpointing keyed by source, universe, design, code, and gate
   hashes. Resume only on an exact identity match.
6. Run tests and static checks before loading outcomes. Then evaluate all 400
   cells sequentially on the consumed 2021-2023 discovery interval, retaining
   explicit invalid reasons and never treating missingness as cash.
7. Apply folds, start dates, frozen neighborhoods, global Bonferroni, and both
   500-repetition native maxT tests only in their preregistered order. Stop early
   when an upstream mandatory gate fails.
8. Freeze the result, write structured local fallback memory with
   `project:quant-agent-team`, `market:cn_a`, and `freq:daily`, run final tests,
   commit, and push. A full survivor may only propose a new prospective shadow
   protocol; no execution or monitoring mutation is authorized.
