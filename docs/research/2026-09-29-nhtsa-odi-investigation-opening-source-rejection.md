# NHTSA ODI investigation-opening source rejection

Decision: **ABANDON_NHTSA_ODI_OPENING_VOLUME_GATE**. The proposed 2021-2023 Office of Defects Investigation opening-resume line is frozen at the source-volume/design gate, before document acquisition, historical-version audit, issuer matching, event-cube access, or any post-availability return read. This line is distinct from the already frozen NHTSA Safety Recall family. The frozen event cube remains a **527-symbol coverage-limited sample, not the full US market**.

## Fixed homogeneous families

The only admissible opening families considered before looking at issuer overlap were:

- `Preliminary Evaluation`, corresponding to PE action numbers; or
- `Engineering Analysis`, corresponding to EA action numbers.

They cannot be pooled. PE is an initial formal evaluation, while EA is a later or upgraded analysis. Audit Queries, Recall Queries, Defect Petitions, Equipment Queries, closing resumes, recalls, technical service bulletins, and consumer complaints are different legal or procedural events and may not be added for volume.

## Official metadata count

NHTSA's official datasets page states that the investigation flat file contains safety-related defect investigations and offers `FLAT_INV.zip` plus the `INV.txt` dictionary. The dictionary defines the NHTSA Action Number, manufacturer, opened date, closed date, recall campaign number, subject, and summary. The official DOT Socrata investigation dataset provides one current row per action number and labels the investigation type.

Official sources:

- https://www.nhtsa.gov/nhtsa-datasets-and-apis
- https://static.nhtsa.gov/odi/ffdd/inv/INV.txt
- https://catalog.data.gov/dataset/investigations-data
- https://data.transportation.gov/resource/b3rp-be92.json

The exact metadata-only Socrata filter was `open_date between '2021-01-01T00:00:00' and '2023-12-31T23:59:59'`. It returned 104 total investigations across all types. The predeclared PE family contained only 59 actions, distributed 23/13/23 in 2021/2022/2023, across 27 displayed manufacturer strings. The EA family contained only 8 actions, distributed 3/2/3, across 6 displayed manufacturer strings.

Neither homogeneous family reaches the fixed high-frequency source floor of 100 total events and 20 events in every training year. PE fails both the total floor and the 2022 floor; EA fails all count floors. Mixing types would change the economic event and is forbidden. Multiple make/model/component rows in the flat file are attributes of one action number, not independent events, and may not be split into pseudo-events.

Because volume fails before the source can qualify, the opening-date/public-posting relation, stable document identifiers, opening-resume byte identity, and amendment/upgrade/closing/replacement chain were not promoted to a full corpus audit. `open_date` is not assumed to equal first web-publication time, and the current daily flat file is not treated as an immutable historical release.

Final state: `source_volume_gate_passed=false`, `preregistered=false`, `investigation_index_persisted=false`, `opening_resume_inventory_acquired=false`, `historical_document_version_audit_performed=false`, `frozen_527_mapping_performed=false`, `event_cube_opened=false`, `cells_completed=0`, `post_availability_outcomes_loaded=false`. Do not reopen by pooling PE/EA/AQ/RQ/DP/EQ, splitting make/model rows, adding closing resumes or recalls, or mapping brands, models, component suppliers, subsidiaries, parents, former names, abbreviations, or aliases. No development or consumed period, strategy version, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.

