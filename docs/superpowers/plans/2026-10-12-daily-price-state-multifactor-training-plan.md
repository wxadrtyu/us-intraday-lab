# Daily price-state multi-factor training plan

1. Add unit tests for primitive definitions, family eligibility, exact 400-cell
   enumeration, strict prior-date mapping, cost/delay accounting, and the
   zero-side-effect output contract.
2. Implement a separate price-state module and CLI without changing the
   rejected v1 module or its immutable evidence.
3. Verify focused tests, lint, and diff checks; commit and push the code-only
   checkpoint before loading any training outcome.
4. Run the diagnostic once against the frozen 2021-2023 inputs and write an
   immutable external cell table plus tracked JSON/Markdown summaries.
5. Freeze the result in local fallback memory with the required project tags,
   verify the repository, commit, and push. Do not load development or consumed
   data and do not create or activate a strategy version.
