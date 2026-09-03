# v13209-v13308 two-asset sleeve diversification

The preregistered batch completed 100 versions and 2,000 parameter cells in
39.79 seconds. No candidate passed every pre-native-null gate; no native null
or Paper-pool change was allowed.

The best candidate passed every gate except cumulative Bonferroni, with
243.97% standard annualized return, 8.27% MDD, IR 3.74, and z 3.066. It chose
top-k one, not the preregistered equal-weight two-asset alternative, so the
proposed diversification did not help. Its adjusted p remained 1.0 across
327,183 accumulated cells.

The batch failed to exceed the original triple-window leader's z of 3.275.
The bounded multi-window optimization program is therefore retired rather
than repeatedly tuning the same structure. All candidates remain rejected
and native null is forbidden. Research resumes at v13309 with a genuinely
different rule-based return source.
