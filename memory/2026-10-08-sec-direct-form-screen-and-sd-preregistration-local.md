# Local fallback memory: SEC direct-form screen and Form SD preregistration

summary: A metadata-only exact-form screen of the 12 frozen official 2021-2023 EDGAR master indexes was completed without outcomes; artifact SHA-256 is c9bfb5fb1755850a0ac3aa2256397513a6d6148a9ddf200555e92052ba51e879. Already frozen families remain closed, and electronic Form 144 was rejected as a comparable source because direct-CIK pairs jump from 22/52 in 2021/2022 to 5,835 in 2023. Exact original Form SD was selected for legal-subtype audit: 3,049 all-market rows and a frozen-sample upper bound of 538 pairs across 185 issuers, yearly 176/180/182, 173 issuers with three filings, and 0.558% maximum concentration. Because Form SD carries both Rule 13p-1 conflict-minerals and Rule 13q-1 resource-extraction reports, official primary bodies will be fetched only to mechanically classify the checked legal rule before coverage. No outcome was opened.

stage: sec-direct-form-screen-and-sd-preregistration

kpi_version: versionless-source-feasibility

tags: project:quant-agent-team, market:cn_a, freq:daily, stage:source-preregistration, strategy:sec-form-sd-conflict-minerals, status:preregistered

next_step: Fetch and hash all direct-CIK exact-original SD filing-index pages and exact SD primary documents sequentially. Classify conflict-minerals only through affirmative Rule 13p-1 and Item 1.01 text, excluding Rule 13q-1 applicable, resource-extraction, dual, ambiguous, amended, missing, or mismatched rows. Map acceptance to the next frozen session, run fixed coverage gates, and reject before outcomes if a three-session state cannot structurally reach the existing 120-signal-session floor. Do not open exhibits, outcomes, development/consumed data, versions, monitoring/Paper, or order routes.
