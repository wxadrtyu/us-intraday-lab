# USDA FSIS recall source rejection

Decision: **ABANDON_FSIS_RECALL_SOURCE**. The proposed 2021–2023 USDA Food Safety and Inspection Service recall line is frozen at the economically homogeneous source-volume gate, before preregistration, recall-index or release acquisition, historical-version audit, company matching, event-cube access, or any post-publication return read. The frozen event cube remains a **527-symbol coverage-limited sample, not the full US market**.

## Official publication and revision semantics

FSIS publishes dated recall releases and public-health alerts with stable identifiers, an announcement date, a company or establishment display name, status, recall reason, and impacted-product details. Current pages can also expose a `Last Updated` date or an Editor's Note describing an expansion or correction. For example, a 2023 recall page states that its quantity, label, and distribution details were expanded after the original announcement.

Those fields make the initial announcement a plausible public event but do not prove that the current page preserves the original bytes or supplies a complete ledger for every update, expansion, correction, closure, and superseded version. That deeper point-in-time audit was not undertaken because every predeclared economically homogeneous recall-reason family fails the earlier frequency screen.

Official references:

- 2021 annual recall summary: https://www.fsis.usda.gov/food-safety/recalls-public-health-alerts/annual-recall-summaries/summary-recall-cases-calendar-8
- 2022 annual recall and PHA summary: https://www.fsis.usda.gov/food-safety/recalls-public-health-alerts/annual-recall-summaries/summary-recall-and-pha-cases
- 2023 annual recall and PHA summary: https://www.fsis.usda.gov/food-safety/recalls-public-health-alerts/annual-recall-summaries/summary-recall-and-pha-cases-0
- FSIS recall and public-health-alert index: https://www.fsis.usda.gov/recalls

## Economically homogeneous source-volume screen

Recalls and public-health alerts are different actions and were not pooled. Within recalls, reasons were evaluated separately so that a product-contamination shock was not mixed after observation with an import, inspection, labeling, allergen, or processing event. The official annual summaries report 47, 45, and 65 recalls overall, but the reason-level counts are:

| Recall reason | 2021 | 2022 | 2023 | Total |
|---|---:|---:|---:|---:|
| Bacillus cereus | 1 | 0 | 0 | 1 |
| Extraneous material | 9 | 9 | 10 | 28 |
| Import violation | 9 | 3 | 16 | 28 |
| Insanitary conditions | 0 | 1 | 0 | 1 |
| Mislabeling | 0 | 1 | 1 | 2 |
| Listeria monocytogenes | 5 | 6 | 5 | 16 |
| STEC | 2 | 3 | 5 | 10 |
| Processing deviations | 0 | 1 | 3 | 4 |
| Produced without inspection | 5 | 10 | 10 | 25 |
| Salmonella | 4 | 0 | 0 | 4 |
| Unapproved substance | 1 | 0 | 0 | 1 |
| Undeclared allergen | 11 | 11 | 15 | 37 |

The fixed high-frequency source-design screen requires at least 100 documents in total and at least 20 documents in every training year before release acquisition or issuer matching. No homogeneous recall-reason family approaches either requirement. Pooling all 157 recalls would cross the aggregate threshold only by combining materially different causal exposures after seeing the counts, which is forbidden. Public-health alerts also cannot be added to rescue volume: they are issued under different circumstances, including when a recall is not requested because products are no longer available for purchase.

Exact legal-company-name matching to frozen SEC issuers, next-session availability, update ambiguity, and missing-release handling could only reduce coverage. The line must not be reopened by pooling recall reasons, adding public-health alerts, counting later updates as new events, or mapping brands, establishment numbers, products, distributors, subsidiaries, parents, former names, abbreviations, fuzzy matches, or manual aliases.

Final state: `source_volume_gate_passed=false`, `historical_release_version_audit_performed=false`, `preregistered=false`, `full_index_persisted=false`, `training_release_inventory_acquired=false`, `frozen_527_mapping_performed=false`, `event_cube_opened=false`, `cells_completed=0`, `post_availability_outcomes_loaded=false`. No development or consumed period, strategy version, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.
