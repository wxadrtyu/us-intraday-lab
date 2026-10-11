# Daily swing multi-factor training plan

1. Add tests for the exact 400-cell grid, trailing-cohort portfolio weights,
   turnover costs, missing-open fail-closed behavior, and output safety fields.
2. Implement the daily swing engine and immutable CLI without changing either
   rejected daily diagnostic.
3. Run focused tests, lint, and diff validation; commit and push before loading
   any swing outcome.
4. Run once on 2021-2023 training data, freeze the cell table and summaries,
   then write tagged local fallback memory and commit/push the result.
5. Recommend separate development acquisition only if the frozen gate passes;
   otherwise reject and continue to a genuinely different technical source.
