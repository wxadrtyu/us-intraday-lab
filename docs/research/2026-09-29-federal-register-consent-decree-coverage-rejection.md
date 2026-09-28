# Federal Register consent-decree coverage rejection

Decision: **ABANDON_FEDERAL_REGISTER_CONSENT_DECREE_COVERAGE_GATE**. The exact preregistered Federal Register inventory and all official GovInfo PDFs were acquired and hash-frozen, but a deliberately permissive current-SEC upper-bound audit still reached only 38 issuers and 94 symbol-document pairs. Both are below the frozen 50-issuer and 200-event floors. The 2021-2023 event cube remains a **527-symbol coverage-limited sample, not the full US market**; it was not opened and no post-publication return was read.

## Immutable source accounting

The exact Federal Register API response is 521,670 bytes with SHA-256 `e5d73a4c3d265448a9f43d3d430319fa973cf95f9d4b15ab41287b5ce1b6bb34`. It reports 320 query results on one page. Applying the preregistered case-insensitive title literal retains 255 unique document numbers and exactly reproduces 96/81/78 documents in 2021/2022/2023.

Every retained API `pdf_url` was fetched sequentially from the official GovInfo publication path. The corpus contains 255 valid PDFs, zero failures, 51,923,632 bytes, and 255 distinct PDF SHA-256 values. The PDF manifest SHA-256 is `f8f726d140fa5688ce0d5b8e649b72c9c9e16e4fd6748e0a04fc78b70a5e3d04`. No FederalRegister.gov HTML, public-inspection draft, DOJ copy, search snippet, or substituted endpoint was used.

## Fail-closed mapping upper bound

The current official SEC company-ticker file was used only to build an upper bound broader than the frozen 527 identities. Its SHA-256 is `affa8f025ab31bab39b60e06cf0bcc401bb87f23151412d686258fc9b99ef091`. The audit applies the preregistered canonicalizer and keeps only one-to-one canonical SEC titles. It then deliberately over-includes every such title found in complete role-bearing sentences and their immediate neighboring sentences, plus case-caption sentences, before public-comment/signature material. This admits background and non-frozen names that the strict defendant/settling-party contract would reject, so a strict frozen-527 result can only be smaller.

The deterministic audit script SHA-256 is `b3696f9a3d0e5737ab6927d736d01a15594ace0055b4606d14f8f6e1b8e3300a`; two consecutive runs produced the same manifest SHA-256 `90b871380d0f1aa8f9e5e25f9c6d649875291e5731bfe3c5fa0552429966ac93`. It processed all 255 PDFs with zero title misses. Its upper bound is:

- 38 current-SEC issuers versus the required 50;
- 94 symbol-document pairs versus the required 200;
- 38/25/31 pairs in 2021/2022/2023;
- family totals of 15 `clean_air`, 29 `clean_water_oil`, 40 `cercla`, 8 `waste_chemicals`, and 2 `general_multi_other`.

The family/year floors also fail in this permissive universe, including `general_multi_other` with no 2021 pair and only one pair in each of 2022 and 2023. Calendar mapping cannot repair issuer, event, family, or family-year shortfalls, so it was not performed. No fuzzy match, alias, brand, d/b/a, former-name, subsidiary, parent, successor, acronym, facility, municipality, individual, or manual override was used.

Final state: `source_complete=true`, `training_pdf_inventory_acquired=true`, `all_current_sec_upper_bound_audit=true`, `frozen_527_mapping_performed=false`, `event_cube_opened=false`, `cells_completed=0`, `post_availability_outcomes_loaded=false`. No development or consumed period, strategy version, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.
