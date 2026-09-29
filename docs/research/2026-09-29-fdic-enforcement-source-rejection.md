# FDIC enforcement decisions and orders source rejection

Decision: **ABANDON_FDIC_ENFORCEMENT_SOURCE**. The proposed 2021–2023 FDIC Enforcement Decisions and Orders line is frozen at the source-volume design gate, before preregistration, order-index acquisition, PDF acquisition, respondent matching, event-cube access, or any post-publication return read. The frozen event cube remains a **527-symbol coverage-limited sample, not the full US market**.

## Official publication semantics

The FDIC's Formal and Informal Enforcement Actions Manual states that section 8(u) requires public disclosure of certain orders and agreements and that the FDIC publishes all final administrative enforcement orders against insured depository institutions and institution-affiliated parties monthly, during the month after issuance. Contemporary FDIC press releases provide an actual release date and enumerate the prior month's orders. The FDIC Archive describes its retained press releases as authentic reproductions reflecting the language and context at publication time and supplies a checksum for the archived release PDF.

Those properties make the monthly release date a plausible conservative availability boundary. They do not, by themselves, prove a complete historical byte/version chain for every individual order PDF, termination, amendment, or superseding action in the current Salesforce-backed order database. That deeper audit was not undertaken because the source fails the earlier structural frequency screen.

Official references:

- FDIC Formal and Informal Enforcement Actions Manual, required publications section: https://www.fdic.gov/regulations/examinations/enforcement-actions/complete-manual.pdf
- FDIC legal-matters transparency statistics: https://www.fdic.gov/about/transparency-accountability-legal-matters
- Example dated monthly release, November 2021 actions: https://www.fdic.gov/news/press-releases/2021/pr21106.html
- FDIC Archive copy of a 2021 monthly release: https://archive.fdic.gov/view/fdic/15532

## Economically homogeneous family screen

The official FDIC transparency table reports the following most frequently issued formal enforcement-action categories. Each category was evaluated separately; combining legally and economically different action types after observing counts was forbidden.

| Homogeneous action category | 2021 | 2022 | 2023 | Total |
|---|---:|---:|---:|---:|
| Consent and cease-and-desist orders | 9 | 21 | 24 | 54 |
| Civil money penalty orders | 26 | 24 | 24 | 74 |
| Removal and prohibition orders | 21 | 25 | 39 | 85 |
| Orders for restitution | 0 | 0 | 0 | 0 |

The fixed high-frequency source-design screen requires at least 100 documents in total and at least 20 documents in every training year before order acquisition or issuer matching. Consent/cease-and-desist orders fail both tests. Civil money penalty orders meet the annual floor but reach only 74 total. Removal/prohibition orders are primarily directed at individuals, are not a valid issuer-level exposure, and still reach only 85 total. No homogeneous family reaches 100.

Even the impermissible union of consent and civil-money-penalty orders would not establish coverage: orders name insured banks or individuals, while the frozen securities universe contains SEC issuers, and the mapping contract forbids inferring a listed bank holding company from a subsidiary bank, branch, brand, former name, or manual alias. Exact respondent-to-frozen-issuer matching and availability checks could only reduce the official gross counts.

Final state: `source_volume_gate_passed=false`, `historical_order_version_audit_performed=false`, `preregistered=false`, `order_index_persisted=false`, `training_pdf_inventory_acquired=false`, `issuer_mapping_performed=false`, `event_cube_opened=false`, `cells_completed=0`, `post_availability_outcomes_loaded=false`. No development or consumed period, strategy version, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.

