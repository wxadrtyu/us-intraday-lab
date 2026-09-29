# USCG Port State Control detention source rejection

Decision: **ABANDON_USCG_PORT_STATE_DETENTION_ENTITY_GATE**. The proposed 2021–2023 U.S. Coast Guard Port State Control detention line is frozen at the issuer-entity structure gate, before preregistration, detention-list acquisition, owner or operator matching, event-cube access, or any post-availability return read. The frozen event cube remains a **527-symbol coverage-limited sample, not the full US market**.

## Official detention publications are vessel-centric

The Coast Guard publishes annual Port State Control reports from 1998 onward and maintains a List of Ships Detained. The official detention page says the list contains vessel name, IMO number, detention date, ship type, port, flag, recognized organization or recognized security organization where applicable, and a deficiency summary. It does not list the full legal owner or operator as a case-level field.

The 2023 annual report records 101 safety, security, or environmental detentions, up from 78 in 2022, so raw event count alone is not the decisive obstacle. The preregistered exposure required the contemporaneously published full owner or operator legal entity to match a frozen SEC issuer mechanically and exactly. Vessel name, IMO number, flag, recognized organization, and deficiency text cannot supply that entity.

Official references:

- USCG Port State Control detentions: https://www.dco.uscg.mil/Our-Organization/Assistant-Commandant-for-Prevention-Policy-CG-5P/Inspections-Compliance-CG-5PC-/Commercial-Vessel-Compliance/Foreign-Offshore-Compliance-Division/Port-State-Control/Detentions/
- USCG Port State Control annual reports: https://www.dco.uscg.mil/Our-Organization/Assistant-Commandant-for-Prevention-Policy-CG-5P/Inspections-Compliance-CG-5PC-/Commercial-Vessel-Compliance/Foreign-Offshore-Compliance-Division/Port-State-Control/Annual-Reports/
- 2023 USCG Port State Control Annual Report: https://www.dco.uscg.mil/Portals/9/DCO%20Documents/5p/CG-5PC/CG-CVC/CVC2/psc/AnnualReports/annualrpt2023a.pdf

## External vessel registries would violate the frozen mapping contract

Turning an IMO number or vessel name into a public issuer requires a separate vessel ownership or management registry and often a chain through registered owners, managers, charterers, subsidiaries, or parents. Those relationships can change over time and are not equivalent roles. The frozen rule forbids using such an external relationship inference, even if a current commercial or public vessel registry could provide it.

The public detention table also includes case status, and annual reports describe detention appeals, including granted appeals. A complete point-in-time design would additionally require immutable snapshots or a case-level correction and appeal ledger. That deeper version audit was not warranted because the official event publication lacks the required legal entity at source. Annual aggregate tables for flags, recognized organizations, and ship managers cannot replace case-level exact issuer identity.

No detention-ground subfamily was counted and no mapping was attempted. The line must not be reopened by converting vessel names or IMO numbers through current registries; treating a flag, recognized organization, manager, charterer, or brand as the owner; following subsidiary or parent chains; using former names, abbreviations, fuzzy matching, or manual aliases; or mixing detentions with deficiencies, bans, marine casualties, safety alerts, or other control regimes to increase coverage.

Final state: `official_detention_index_exists=true`, `issuer_entity_structure_gate_passed=false`, `preregistered=false`, `detention_lists_acquired=false`, `event_family_counted=false`, `frozen_527_mapping_performed=false`, `event_cube_opened=false`, `cells_completed=0`, `post_availability_outcomes_loaded=false`. No development or consumed period, strategy version, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.
