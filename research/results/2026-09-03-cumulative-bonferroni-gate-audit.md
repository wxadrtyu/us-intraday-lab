# Cumulative Bonferroni gate audit

The active research contract requires cumulative Bonferroni p below 0.05 in
addition to all performance, robustness, consumed-period, and native-null
checks. The inherited evaluator instead used `prospective_z_score_at_least_3`
for versions after v7795 while still reporting the actual Bonferroni value.

Consequences:

- v11800 reported z=3.196 and cumulative Bonferroni p=1.0. It remains valuable
  as a parity-proven research artifact but is rejected for admission.
- v11881 reported z=3.116 and cumulative Bonferroni p=1.0. It is rejected
  before native null; v11909 is therefore not consumed as a validation version.
- The original batch artifacts are retained. Corrected audits are written as
  supplements rather than rewriting the observed outputs.

Starting with the corrected v11809 evaluator and subsequent campaigns, the
literal cumulative Bonferroni p<0.05 gate is restored and cannot be replaced
by the z>=3 screen.
