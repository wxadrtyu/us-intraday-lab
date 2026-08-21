"""Audit the full v59-v145 component frontier before v349+ portfolio search.

Selection is frozen on 2022-2025 development evidence.  Historical coverage and
consumed 2026 are attached only after development selection; consumed 2026 is
never part of the component ranking.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import analyze_full_universe_intraday_v53_cross_asset_factors as v53
import evaluate_full_universe_intraday_v44_multihorizon_confirmation as v44
import evaluate_full_universe_intraday_v47_score_slope as v47
import evaluate_full_universe_intraday_v146_v245_anchored_ensembles as anchored
import search_full_universe_intraday_v12_robustness as v12
import search_full_universe_intraday_v13_regime_rotation as v13
import validate_full_universe_intraday_v246_component_factory_null as native_null

from us_intraday_lab.validation.null_tests import (
    HoldingRuleScoringConfig,
    NullTestConfig,
    run_null_tests,
)
from us_intraday_lab.validation.stability import TQQQ_SOXL_SYMBOLS


def _components(source_dir: Path) -> list[dict]:
    records: list[dict] = []
    for version in range(59, 146):
        payload = json.loads(
            (source_dir / f"full-universe-intraday-v{version}-exact.json").read_text(
                encoding="utf-8"
            )
        )
        records.extend(payload["records"])
    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    started = time.perf_counter()

    development = v53.Cube(args.root, "alpaca", 0)
    historical = v53.Cube(args.root, "historical", 0)
    models = v44._fit(development, (20, 23, 26, 29), 72)
    anchor_development = anchored._v45_streams(development, models)
    anchor_historical = anchored._v45_streams(historical, models)[0]
    selected: list[dict] = []

    for index, record in enumerate(_components(args.source_dir), start=1):
        component_development = anchored._component_streams(development, record)
        component_historical = anchored._component_streams(historical, record)[0]
        cells = []
        for weight in anchored.V45_WEIGHTS:
            streams = tuple(
                anchored._blend(anchor, component, weight)
                for anchor, component in zip(anchor_development, component_development, strict=True)
            )
            standard, cost, delay = [v47._observe(development, stream, True) for stream in streams]
            historical_stream = anchored._blend(anchor_historical, component_historical, weight)
            historical_observation = v47._observe(historical, historical_stream, True)[
                "historical_2018_2020"
            ]
            cells.append(
                {
                    "weight": weight,
                    "standard": standard,
                    "cost": cost,
                    "delay": delay,
                    "historical": historical_observation,
                    "development_pass": all(
                        v13._primary(observation) for observation in (standard, cost, delay)
                    ),
                    "historical_pass": (
                        float(historical_observation["annualized_return"]) > 0
                        and float(historical_observation["max_drawdown"]) < 0.20
                    ),
                }
            )
        qualifying = [
            cell for cell in cells if cell["development_pass"] and cell["historical_pass"]
        ]
        if qualifying:
            # Development rank only.  Historical is a pass/fail robustness check and
            # consumed 2026 is deliberately absent from this ordering.
            best = max(
                qualifying,
                key=lambda cell: min(
                    float(cell[name]["development_oos_2024_2025"]["annualized_return"])
                    for name in ("standard", "cost", "delay")
                ),
            )
            selected.append(
                {
                    "component_candidate_id": record["candidate_id"],
                    "record": record,
                    "best_weight": best["weight"],
                    "development_score": min(
                        float(best[name]["development_oos_2024_2025"]["annualized_return"])
                        for name in ("standard", "cost", "delay")
                    ),
                    "anchored_standard": best["standard"],
                    "anchored_cost_18bp": best["cost"],
                    "anchored_delay_5min": best["delay"],
                    "anchored_historical": best["historical"],
                }
            )
        if index % 50 == 0:
            print(f"economic screen {index}/435 selected={len(selected)}", flush=True)

    selected.sort(key=lambda item: item["development_score"], reverse=True)
    config = NullTestConfig(
        seed=native_null.NULL_SEED,
        repetitions=native_null.NULL_REPETITIONS,
        percentile=native_null.NULL_PERCENTILE,
        symbols=TQQQ_SOXL_SYMBOLS,
    )
    scoring = HoldingRuleScoringConfig(
        scoring_id="v349-component-frontier-null",
        rule_version="development-selected-ridge-component-v2",
        cost_model_id="standard-9bp-v1",
        max_entries_per_session=1,
        max_concurrent_positions=1,
    )
    results = []
    for index, item in enumerate(selected, start=1):
        result = run_null_tests(
            native_null._opportunities(development, item.pop("record")),
            config=config,
            scoring_config=scoring,
        )
        item["component_factory_null"] = native_null._result_payload(result)
        results.append(item)
        if result.passed or index % 10 == 0:
            print(
                f"native null {index}/{len(selected)} passes="
                f"{sum(value['component_factory_null']['passed'] for value in results)}",
                flush=True,
            )

    output = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "selection_contract": (
            "components are screened and ranked on 2022-2025 development evidence; "
            "2018-2020 is pass/fail only; consumed 2026 is attached inside frozen "
            "observations and is never used for ranking"
        ),
        "component_count": 435,
        "economically_eligible_components": len(selected),
        "factory_null_passes": sum(item["component_factory_null"]["passed"] for item in results),
        "elapsed_seconds": time.perf_counter() - started,
        "results": results,
    }
    v12._atomic(args.output, output)
    print(json.dumps({key: value for key, value in output.items() if key != "results"}, indent=2))


if __name__ == "__main__":
    main()
