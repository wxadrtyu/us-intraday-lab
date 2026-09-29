# EPA Federal Register administrative-settlement source rejection

Decision: **ABANDON_EPA_FR_ADMINISTRATIVE_SETTLEMENT_SOURCE**. The proposed 2021–2023 EPA Federal Register administrative consent/settlement line is frozen at the source-volume design gate, before preregistration, PDF acquisition, issuer matching, event-cube access, or any post-publication return read. The frozen event cube remains a **527-symbol coverage-limited sample, not the full US market**.

## Point-in-time source contract

The publication channel itself is suitable. FederalRegister.gov documents that its API is public and keyless, while also warning that its XML/HTML rendition is informational and that legal research should be verified against the official GovInfo PDF. The admissible content would therefore have been the official GovInfo publication PDF identified by stable Federal Register document number, with availability conservatively set to the first frozen-sample trading session strictly after `publication_date`. Public-inspection drafts, EPA copies, snippets, and later HTML would not have been substitutes.

Official references:

- Federal Register API documentation: https://www.federalregister.gov/developers/documentation/api/v1
- Official Federal Register collection on GovInfo: https://www.govinfo.gov/app/collection/FR

## Economically homogeneous family screen

The candidate was deliberately limited to CERCLA administrative settlement agreements/orders on consent. It was not allowed to mix Clean Air Act, Clean Water Act, FIFRA, TSCA, RCRA, rulemaking, permit, citizen-suit, or unrelated consent notices merely to add observations.

Four read-only official API probes covered EPA documents published from 2021-01-01 through 2023-12-31. A deterministic case-insensitive title filter was applied after each full one-page response (`per_page=1000`):

| Official full-text term | API hits | Titles consistent with the candidate wording | 2021 / 2022 / 2023 |
|---|---:|---:|---:|
| `administrative settlement agreement` | 140 | 43 | 12 / 11 / 20 |
| `settlement agreement order on consent` | 68 | 14 | 7 / 2 / 5 |
| `consent agreement final order` | 133 | 0 | 0 / 0 / 0 |
| `administrative penalty` | 207 | 0 | 0 / 0 / 0 |

The 43-title inventory is deliberately over-inclusive: it still contains prospective-purchaser arrangements, de minimis/cashout settlements, response-action agreements, and records that would be excluded by a single fixed economic exposure. It is therefore a hard upper bound, not usable coverage. The stricter `order on consent` wording leaves only 14 notices and just two in 2022.

This research program requires a genuinely high-frequency, economically homogeneous announcement family before undertaking issuer mapping or a fixed 400-cell evaluation. A gross ceiling of 43 documents over three years, with no year above 20, cannot support a minimum design screen of 100 documents and 20 documents in every year; exact respondent-to-frozen-issuer matching, duplicate/correction removal, and trading-calendar availability can only reduce it. No family definition or threshold was changed after observing the shortfall.

Final state: `source_publication_semantics_feasible=true`, `economic_family_feasible=false`, `preregistered=false`, `api_corpus_persisted=false`, `training_pdf_inventory_acquired=false`, `issuer_mapping_performed=false`, `event_cube_opened=false`, `cells_completed=0`, `post_availability_outcomes_loaded=false`. No development or consumed period, strategy version, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.
