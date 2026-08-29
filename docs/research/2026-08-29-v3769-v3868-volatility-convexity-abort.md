# v3769-v3868 volatility-convexity campaign abort

## Decision

Abort before outcome scanning. The first attempted cell failed before evaluation because the base cube already contained a factor named `leverage_residual`, which caused the extension guard to return before registering the other proposed factors. No valid cell, frontier record, or outcome was produced.

Repository review then established that v3169-v3268 had already completed 12,800 cells on the same leveraged-versus-underlying residual source, including residual reversal/continuation, volatility contraction, flow, dispersion and breakout confirmation. Running v3769-v3868 after repairing the implementation would therefore duplicate a previously falsified economic family rather than test a genuinely new source.

- Reserved versions: v3769-v3868
- Valid evaluated cells: 0
- Outcome data inspected: none
- Candidate admissions: 0
- Paper-pool changes: none

The cache guard is repaired for reproducibility, but this campaign remains intentionally unexecuted. The next campaign advances to unused version numbers and changes the mechanism to paired-underlying-confirmed post-entry risk timing on the frozen v1254 entry strategy.

