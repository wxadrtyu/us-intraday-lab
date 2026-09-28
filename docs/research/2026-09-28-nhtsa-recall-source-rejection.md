# NHTSA recall source rejection

Decision: **ABANDON_NHTSA_RECALL_SOURCE**. This line is frozen during preregistration design, before bulk/API acquisition, Part 573 document inventory, manufacturer mapping, event-cube access, or any post-event return read. The frozen 2021–2023 event cube remains a **527-symbol coverage-limited sample, not the full US market**.

## Official-source audit

NHTSA's [Datasets and APIs](https://www.nhtsa.gov/nhtsa-datasets-and-apis) page describes the recall dataset as daily-frequency, 1949-to-present current data. It links the current `FLAT_RCL_POST_2010.zip` snapshot and says manufacturers must notify NHTSA within five business days and file Part 573 defect/noncompliance reports.

The official [recall import guide](https://static.nhtsa.gov/odi/ffdd/rcl/Import_Instructions_Recalls.pdf) defines `RCDATE` as **Report Received Date** and `DATEA` as **Record Creation Date**. It describes a growing current database rather than dated historical vintages. The public download page shows old-range ZIP objects updated in 2026, so current object modification time cannot stand in for their historical public state.

NHTSA's official recall guidance explains the sequence: ODI receives the Part 573 report, assigns a recall number, communicates it to the manufacturer, later sends a written acknowledgment, then summarizes and enters the recall into the public ODI system. It does not state that `RCDATE`, `DATEA`, recall-number assignment, acknowledgment, public-database entry, and first web publication occur at the same timestamp.

## Point-in-time and version failure

Using `RCDATE` as a public timestamp would backdate availability to agency receipt without proof that the record or Part 573 document was public then. `DATEA` is a database record-creation field, not an officially defined public-posting timestamp. A next-session rule cannot be assigned honestly from either field.

Part 573 reports can be followed by additional information and revised recall scope, remedy, or schedule. Current stable-looking PDF URLs and campaign numbers prove only current retrievability. The public bulk/API documentation audited here provides no complete historical ledger tying every original and amended document byte sequence to an exact first-publication timestamp. Current daily snapshots therefore cannot reconstruct the 2021–2023 first-public state without inference.

Strict issuer mapping is also structurally fragile because the flat file distinguishes `MFGNAME` (manufacturer that filed) from `MFGTXT` (manufacturer of recalled products), while brand, make, importer, equipment supplier, subsidiary, and parent inference are forbidden. Mapping is not attempted because the public-time and version gates already fail.

Final state: `preregistered=false`, `bulk_or_api_acquired=false`, `part573_inventory_acquired=false`, `issuer_mapping_performed=false`, `event_cube_opened=false`, `cells_completed=0`, `post_availability_outcomes_loaded=false`. No development or consumed period, strategy version, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.
