# SEC trading-suspension orders source rejection

Decision: **ABANDON_SEC_TRADING_SUSPENSION_SOURCE**. The proposed 2021–2023 SEC Trading Suspension Orders line is frozen at the source-volume design gate, before preregistration, complete index or order acquisition, historical-version audit, issuer matching, event-cube access, or any post-publication return read. The frozen event cube remains a **527-symbol coverage-limited sample, not the full US market**.

## Official source and event identity

The SEC's official Trading Suspensions index describes a Commission suspension as an investor-protection action lasting up to ten trading days. Its year filters expose the suspension date, respondent display name, Exchange Act release number, and an official order link. The 2023 order for Tingo Group, Inc., for example, is identified as Release No. 34-98920 and the official PDF is dated November 13, 2023. Contemporaneous SEC “What's New” pages also list trading-suspension releases by release number.

These properties make the family legally homogeneous and provide promising document identity. They do not by themselves establish that the current index and current PDF bytes reproduce every document's first web-publication state, or provide a complete correction, rescission, extension, replacement, and superseded-byte ledger. That deeper point-in-time audit was not undertaken because the source fails the earlier structural frequency screen.

Official references:

- SEC Trading Suspensions index: https://www.sec.gov/enforcement-litigation/trading-suspensions
- 2021 year-filtered index: https://www.sec.gov/enforcement-litigation/trading-suspensions?month=All&order=field_publish_date&populate=&sort=asc&year=2021
- 2022 year-filtered index: https://www.sec.gov/enforcement-litigation/trading-suspensions?month=All&order=field_publish_date&populate=&sort=asc&year=2022
- 2023 year-filtered index: https://www.sec.gov/enforcement-litigation/trading-suspensions?aId=edit-year&populate=&year=2023
- Example official Tingo Group order PDF: https://www.sec.gov/files/litigation/suspensions/2023/34-98920-o.pdf
- Example contemporaneous SEC “What's New” page: https://www.sec.gov/news/whatsnew/2021/wn012191.shtml

## Source-volume gate

The official year-filtered indexes report the following document rows:

| Training year | Trading-suspension order rows |
|---|---:|
| 2021 | 102 |
| 2022 | 2 |
| 2023 | 4 |
| **Total** | **108** |

The 2022 index contains only Digatrade Financial Corporation (34-95156) and Viabuilt Ventures, Inc. (34-95397). The 2023 index contains only TOP Financial Group Limited (34-97493), Green Automotive Company (34-98519), Tingo Group, Inc. (34-98920), and Agri-Fintech Holdings, Inc. (34-98921).

The fixed high-frequency source-design screen requires at least 100 documents in total and at least 20 documents in every training year before document acquisition or issuer matching. Although the three-year total is 108, the family fails decisively in 2022 and 2023. An index row may name multiple respondents, but splitting a single Commission order into multiple pseudo-events cannot create independent publication events and is forbidden. Exact order-caption legal-entity matching to the frozen 527 issuers, next-session availability, ambiguity rejection, and missing-PDF handling could only reduce coverage.

The line must not be reopened by adding older years, inferring issuer identity from a ticker, splitting mass-suspension orders, mixing other SEC order families, or using brands, subsidiaries, parents, former names, abbreviations, fuzzy matches, or manual aliases.

Final state: `source_volume_gate_passed=false`, `historical_order_version_audit_performed=false`, `preregistered=false`, `full_index_persisted=false`, `training_pdf_inventory_acquired=false`, `frozen_527_mapping_performed=false`, `event_cube_opened=false`, `cells_completed=0`, `post_availability_outcomes_loaded=false`. No development or consumed period, strategy version, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.
