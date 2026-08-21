"""v349-v448: preregistered state enhancements and independent alpha rules."""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path

import evaluate_full_universe_intraday_v248_v347_mechanism_campaign as prior

FIRST_VERSION = 349
LAST_VERSION = 448
PRIOR_COMPARISON_CELLS = 31_510

# Fifty anchor enhancements: 25 economically distinct state hypotheses at two
# causal clocks.  Coefficients are fixed before any v349+ evaluation.
STATE_CONCEPTS = (
    ("broad_index_confirmation", {"qqq_current": 1.0, "iwm_current": 1.0}),
    ("large_over_small_risk", {"qqq_current": 1.0, "iwm_current": -1.0}),
    ("small_over_large_risk", {"iwm_current": 1.0, "qqq_current": -1.0}),
    ("trend_with_breadth", {"spy_current": 1.0, "sector_breadth": 1.0}),
    ("trend_with_low_dispersion", {"spy_current": 1.0, "sector_dispersion": -1.0}),
    ("trend_with_cyclicals", {"spy_current": 1.0, "cyclical_minus_defensive": 1.0}),
    ("trend_with_tech", {"spy_current": 1.0, "tech_minus_market": 1.0}),
    ("trend_with_agreement", {"spy_current": 1.0, "risk_asset_agreement": 1.0}),
    ("calm_breadth", {"spy_volatility": -1.0, "sector_breadth": 1.0}),
    ("calm_agreement", {"spy_volatility": -1.0, "risk_asset_agreement": 1.0}),
    ("calm_technology", {"spy_volatility": -1.0, "tech_minus_market": 1.0}),
    ("calm_cyclicals", {"spy_volatility": -1.0, "cyclical_minus_defensive": 1.0}),
    ("breadth_low_dispersion", {"sector_breadth": 1.0, "sector_dispersion": -1.0}),
    ("breadth_agreement", {"sector_breadth": 1.0, "risk_asset_agreement": 1.0}),
    ("breadth_technology", {"sector_breadth": 1.0, "tech_minus_market": 1.0}),
    ("breadth_cyclicals", {"sector_breadth": 1.0, "cyclical_minus_defensive": 1.0}),
    ("cyclical_tech_confirmation", {"cyclical_minus_defensive": 1.0, "tech_minus_market": 1.0}),
    ("cyclical_without_vol", {"cyclical_minus_defensive": 1.0, "spy_volatility": -1.0}),
    ("tech_without_dispersion", {"tech_minus_market": 1.0, "sector_dispersion": -1.0}),
    ("agreement_without_dispersion", {"risk_asset_agreement": 1.0, "sector_dispersion": -1.0}),
    ("three_way_risk_on", {"spy_current": 1.0, "sector_breadth": 1.0, "risk_asset_agreement": 1.0}),
    (
        "three_way_calm_trend",
        {"spy_current": 1.0, "spy_volatility": -1.0, "sector_dispersion": -1.0},
    ),
    ("three_way_growth", {"qqq_minus_iwm": 1.0, "tech_minus_market": 1.0, "sector_breadth": 1.0}),
    (
        "three_way_reflation",
        {"iwm_current": 1.0, "cyclical_minus_defensive": 1.0, "sector_breadth": 1.0},
    ),
    (
        "defensive_stress_avoidance",
        {"spy_current": 1.0, "spy_volatility": -1.0, "cyclical_minus_defensive": 1.0},
    ),
)
STATE_CLOCKS = ("bar17", "prior_close")

# Fifty independent versions: ten distinct factor mechanisms at five causal
# entry/exit schedules.  Parameter tuning remains inside each version.
RULE_FAMILIES = (
    (
        "opening_trend_quality",
        ("current_return", "recent_return", "path_efficiency", "close_location"),
        (1, 1, 1, 1),
    ),
    (
        "flow_confirmed_strength",
        ("current_return", "relative_return", "signed_volume_imbalance", "volume_acceleration"),
        (1, 1, 1, -1),
    ),
    (
        "compressed_breakout",
        ("current_return", "realized_volatility", "path_efficiency"),
        (1, -1, 1),
    ),
    (
        "gap_continuation_quality",
        ("gap", "current_return", "close_location", "path_efficiency"),
        (1, 1, 1, 1),
    ),
    (
        "gap_fade_recovery",
        ("gap", "recent_return", "relative_return", "close_location"),
        (-1, 1, 1, 1),
    ),
    (
        "vwap_flow_reclaim",
        ("vwap_distance", "signed_volume_imbalance", "close_location"),
        (1, 1, 1),
    ),
    (
        "residual_efficient_strength",
        ("leverage_residual", "path_efficiency", "current_rank"),
        (1, 1, 1),
    ),
    ("prior_laggard_recovery", ("prior20_rank", "prior20_return", "recent_return"), (-1, -1, 1)),
    (
        "cross_section_acceleration",
        ("current_rank", "relative_return", "volume_acceleration"),
        (1, 1, -1),
    ),
    (
        "balanced_six_factor",
        (
            "current_return",
            "recent_return",
            "relative_return",
            "path_efficiency",
            "signed_volume_imbalance",
            "close_location",
        ),
        (1, 1, 1, 1, 1, 1),
    ),
)
RULE_SCHEDULES = ((11, 26), (20, 41), (26, 50), (35, 65), (47, 75))


def specifications() -> list[tuple]:
    return [("state", concept, clock) for clock in STATE_CLOCKS for concept in STATE_CONCEPTS] + [
        ("rule", family, schedule) for schedule in RULE_SCHEDULES for family in RULE_FAMILIES
    ]


def _failed_gates(records: list[dict]) -> Counter[str]:
    failures: Counter[str] = Counter()
    for record in records:
        for name, passed in record["gates"].items():
            if not passed:
                failures[name] += 1
        if record["pre_factory_null_pass"]:
            failures["native_factory_null_required"] += 1
    return failures


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    development = prior.v53.Cube(args.root, "alpaca", 0)
    historical = prior.v53.Cube(args.root, "historical", 0)
    anchor_models = prior.v44._fit(development, (20, 23, 26, 29), 72)
    anchor_raw = tuple(
        prior.v45._stream(development, anchor_models, 72, "reliability", 0.75, 2, cost, delay)
        for cost, delay in (
            (prior.v34.STANDARD_COST, 0),
            (prior.v34.STRESS_COST, 0),
            (prior.v34.STANDARD_COST, 1),
        )
    )
    anchor_development = tuple(
        prior.v42._scaled(
            stream,
            prior.v42._exposure(anchor_raw[0].values, 15, 0.35, 0.0),
        )
        for stream in anchor_raw
    )
    historical_raw = prior.v45._stream(
        historical, anchor_models, 72, "reliability", 0.75, 2, prior.v34.STANDARD_COST, 0
    )
    anchor_historical = prior.v42._scaled(
        historical_raw,
        prior.v42._exposure(historical_raw.values, 15, 0.35, 0.0),
    )
    planned_new_cells = len(STATE_CONCEPTS) * len(STATE_CLOCKS) * len(prior.STATE_QUANTILES) + len(
        RULE_FAMILIES
    ) * len(RULE_SCHEDULES) * len(prior.RULE_QUANTILES) * len(prior.CONFIRMATIONS) * len(
        prior.TARGETS
    ) * len(prior.LOOKBACKS)
    total_cells = PRIOR_COMPARISON_CELLS + planned_new_cells
    specs = specifications()
    if len(specs) != 100 or len({json.dumps(item, sort_keys=True) for item in specs}) != 100:
        raise RuntimeError("campaign must preregister exactly 100 independent versions")
    versions: list[dict] = []
    all_records: list[dict] = []
    for offset in range(len(specs)):
        version = FIRST_VERSION + offset
        path = args.output_dir / f"full-universe-intraday-v{version}-exact.json"
        if not path.exists():
            break
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("status") != "COMPLETE" or payload.get("version") != version:
            raise RuntimeError(f"invalid resumable artifact for v{version}")
        records = payload["records"]
        all_records.extend(records)
        versions.append(
            {
                "version": version,
                "kind": "state" if version < FIRST_VERSION + 50 else "rule",
                "economic_hypothesis": payload["economic_hypothesis"],
                "cells": payload["scan"]["evaluated_cells"],
                "pre_factory_null_hits": payload["pre_factory_null_hits"],
                "all_reference_gate_hits": payload["all_reference_gate_hits"],
                "rejection_reason_counts": payload["rejection_reason_counts"],
                "best_candidate_id": records[0]["candidate_id"],
                "best_oos_annualized_return": records[0]["standard"]["development_oos_2024_2025"][
                    "annualized_return"
                ],
                "best_consumed_2026_total_return": records[0]["standard"]["consumed_2026_all"][
                    "total_return"
                ],
            }
        )
    resume_offset = len(versions)
    for offset, specification in enumerate(specs[resume_offset:], start=resume_offset):
        version = FIRST_VERSION + offset
        version_started = time.perf_counter()
        kind = str(specification[0])
        if kind == "state":
            cells = prior._state_cells(
                development,
                historical,
                anchor_development,
                anchor_historical,
                specification[1],
                str(specification[2]),
            )
            hypothesis = str(specification[1][0]) + " at " + str(specification[2])
        else:
            cells = prior._rule_cells(development, historical, specification[1], specification[2])
            hypothesis = str(specification[1][0]) + " over bars " + str(specification[2])
        cells.sort(key=lambda item: item["rank"], reverse=True)
        records = [
            prior._record(development, historical, version, kind, cells, cell, total_cells)
            for cell in cells[:3]
        ]
        all_records.extend(records)
        payload = {
            "schema_version": "1.0.0",
            "status": "COMPLETE",
            "version": version,
            "research_class": "admitted_strategy_enhancement"
            if kind == "state"
            else "independent_return_source",
            "economic_hypothesis": hypothesis,
            "selection_contract": "2022-2025 selection only; 2026 consumed diagnostic attached after frontier freeze",
            "scan": {
                "evaluated_cells": len(cells),
                "frozen_frontier": 3,
                "elapsed_seconds": time.perf_counter() - version_started,
            },
            "pre_factory_null_hits": sum(record["pre_factory_null_pass"] for record in records),
            "all_reference_gate_hits": sum(
                record["all_reference_gates_pass"] for record in records
            ),
            "rejection_reason_counts": dict(_failed_gates(records)),
            "records": records,
        }
        prior.v12._atomic(
            args.output_dir / f"full-universe-intraday-v{version}-exact.json", payload
        )
        versions.append(
            {
                "version": version,
                "kind": kind,
                "economic_hypothesis": hypothesis,
                "cells": len(cells),
                "pre_factory_null_hits": payload["pre_factory_null_hits"],
                "all_reference_gate_hits": payload["all_reference_gate_hits"],
                "rejection_reason_counts": payload["rejection_reason_counts"],
                "best_candidate_id": records[0]["candidate_id"],
                "best_oos_annualized_return": records[0]["standard"]["development_oos_2024_2025"][
                    "annualized_return"
                ],
                "best_consumed_2026_total_return": records[0]["standard"]["consumed_2026_all"][
                    "total_return"
                ],
            }
        )
        failures = _failed_gates(all_records)
        summary = {
            "schema_version": "1.0.0",
            "status": "RUNNING" if version < LAST_VERSION else "COMPLETE",
            "version_range": [FIRST_VERSION, LAST_VERSION],
            "planned_versions": 100,
            "completed_versions": offset + 1,
            "enhancement_versions": sum(item["kind"] == "state" for item in versions),
            "independent_return_source_versions": sum(item["kind"] == "rule" for item in versions),
            "planned_new_cells": planned_new_cells,
            "cumulative_comparison_cells": total_cells,
            "pre_factory_null_hits": sum(record["pre_factory_null_pass"] for record in all_records),
            "admitted_before_factory_null": 0,
            "rejected_frontier_records": len(all_records),
            "rejection_reason_counts": dict(failures),
            "elapsed_seconds": time.perf_counter() - started,
            "versions": versions,
        }
        prior.v12._atomic(args.summary, summary)
        print(
            json.dumps(
                {
                    "progress": f"{offset + 1}/100",
                    "version": version,
                    "kind": kind,
                    "pre_factory_null_hits": versions[-1]["pre_factory_null_hits"],
                    "best_oos_annualized_return": versions[-1]["best_oos_annualized_return"],
                    "best_consumed_2026_total_return": versions[-1][
                        "best_consumed_2026_total_return"
                    ],
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
