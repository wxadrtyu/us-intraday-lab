"""v753-v852 preregistered dual-component routing around frozen v45."""

from __future__ import annotations

import argparse
import itertools
import json
import math
import time
from collections import Counter
from pathlib import Path

import evaluate_full_universe_intraday_v146_v245_anchored_ensembles as anchored
import evaluate_full_universe_intraday_v248_v347_mechanism_campaign as prior
import numpy as np
import pandas as pd

from us_intraday_lab.fast_intraday_research import metrics

FIRST_VERSION = 753
LAST_VERSION = 852
PRIOR_COMPARISON_CELLS = 65_994
TOTAL_WEIGHTS = (0.02, 0.04, 0.06, 0.08, 0.10)
V247_SHARES = (0.0, 0.25, 0.50, 0.75, 1.0)
STATE_QUANTILES = (0.20, 0.35, 0.50, 0.65)
COMPONENT_IDS = {
    "v247": "lev-v118-5d4329ecaa7a2114",
    "v449": "lev-v60-b528b229cefeace2",
}
ROUTE_ANCHOR = False
REALLOCATE_TO_ANCHOR_WHEN_BLOCKED = False
RANK_MODE = "legacy"
ROUTING_MODES = (
    ("static", None, {}),
    (
        "prior_close_orderly_market",
        "prior_close",
        {
            "spy_current": 1.0,
            "sector_breadth": 1.0,
            "risk_asset_agreement": 1.0,
            "spy_volatility": -1.0,
        },
    ),
    (
        "bar17_orderly_market",
        "bar17",
        {
            "spy_current": 1.0,
            "sector_breadth": 1.0,
            "risk_asset_agreement": 1.0,
            "sector_dispersion": -1.0,
        },
    ),
    (
        "prior_close_orderly_growth",
        "prior_close",
        {
            "qqq_current": 1.0,
            "tech_minus_market": 1.0,
            "spy_volatility": -1.0,
            "sector_dispersion": -1.0,
        },
    ),
)


def _atomic(path: Path, payload: dict) -> None:
    prior.v12._atomic(path, payload)


def _component_record(source_dir: Path, candidate_id: str) -> dict:
    version = int(candidate_id.split("-")[1][1:])
    payload = json.loads(
        (source_dir / f"full-universe-intraday-v{version}-exact.json").read_text(
            encoding="utf-8"
        )
    )
    for record in payload["records"]:
        if record["candidate_id"] == candidate_id:
            return record
    raise RuntimeError(f"FROZEN_COMPONENT_NOT_FOUND:{candidate_id}")


def _state_allowed(
    development: prior.v53.Cube,
    historical: prior.v53.Cube,
    clock: str | None,
    coefficients: dict[str, float],
) -> list[tuple[float | None, np.ndarray, np.ndarray]]:
    if clock is None:
        return [
            (
                None,
                np.ones(len(development.sessions), dtype=bool),
                np.ones(len(historical.sessions), dtype=bool),
            )
        ]
    train = development.masks()["train_2022_2023"]
    dev_matrix = prior._state_matrix(development, clock)
    hist_matrix = prior._state_matrix(historical, clock)
    means = {name: float(np.nanmean(dev_matrix[name][train])) for name in coefficients}
    scales = {
        name: max(1e-8, float(np.nanstd(dev_matrix[name][train]))) for name in coefficients
    }
    dev_score = prior._state_score(dev_matrix, coefficients, means, scales)
    hist_score = prior._state_score(hist_matrix, coefficients, means, scales)
    finite_train = dev_score[train & np.isfinite(dev_score)]
    return [
        (
            float(np.quantile(finite_train, quantile)),
            np.isfinite(dev_score) & (dev_score >= np.quantile(finite_train, quantile)),
            np.isfinite(hist_score) & (hist_score >= np.quantile(finite_train, quantile)),
        )
        for quantile in STATE_QUANTILES
    ]


def _route(stream: prior.v12.ReturnStream, allowed: np.ndarray) -> prior.v12.ReturnStream:
    return prior._mask_stream(stream, allowed)


def _blend(
    anchor: prior.v12.ReturnStream,
    v247: prior.v12.ReturnStream,
    v449: prior.v12.ReturnStream,
    *,
    total_weight: float,
    v247_share: float,
    allowed: np.ndarray | None = None,
) -> prior.v12.ReturnStream:
    if REALLOCATE_TO_ANCHOR_WHEN_BLOCKED:
        if allowed is None:
            raise RuntimeError("REALLOCATION_REQUIRES_ALLOWED_MASK")
        routed_weight = np.where(allowed, total_weight, 0.0)
    else:
        routed_weight = total_weight
    anchor_weight = 1.0 - routed_weight
    v247_weight = routed_weight * v247_share
    v449_weight = routed_weight * (1.0 - v247_share)
    return prior.v12.ReturnStream(
        anchor_weight * anchor.values + v247_weight * v247.values + v449_weight * v449.values,
        anchor_weight * anchor.benchmark
        + v247_weight * v247.benchmark
        + v449_weight * v449.benchmark,
        anchor.active | v247.active | v449.active,
        anchor.component_trades + v247.component_trades + v449.component_trades,
    )


def _primary(observations: dict) -> bool:
    oos = observations["development_oos_2024_2025"]
    return (
        float(oos["annualized_return"]) >= 0.50
        and float(oos["max_drawdown"]) < 0.20
        and float(oos["information_ratio"]) >= 1.0
        and all(
            float(observations[name]["annualized_return"]) > 0
            for name in ("train_2022_2023", "2024", "2025")
        )
    )


def _rank(observations: tuple[dict, dict, dict]) -> tuple[float, ...]:
    if RANK_MODE == "legacy":
        return prior.v47._rank(*observations)
    if RANK_MODE != "stress_floor":
        raise RuntimeError(f"UNKNOWN_RANK_MODE:{RANK_MODE}")
    oos = [item["development_oos_2024_2025"] for item in observations]
    return (
        min(float(item["annualized_return"]) for item in oos),
        -max(float(item["max_drawdown"]) for item in oos),
        min(float(item["information_ratio"]) for item in oos),
        min(
            float(observations[0][name]["annualized_return"])
            for name in ("train_2022_2023", "2024", "2025")
        ),
    )


def _record(
    development: prior.v53.Cube,
    historical: prior.v53.Cube,
    version: int,
    cells: list[dict],
    selected: dict,
    cumulative_cells: int,
) -> dict:
    standard, cost, delay = [prior.v47._observe(development, stream, True) for stream in selected["streams"]]
    historical_obs = prior.v47._observe(historical, selected["historical_stream"], True)[
        "historical_2018_2020"
    ]
    folds = [
        metrics(
            selected["streams"][0].values[index],
            selected["streams"][0].benchmark[index],
            selected["streams"][0].active[index],
        )
        for index in np.array_split(np.flatnonzero(development.masks()["development_all"]), 5)
    ]
    starts = {}
    for start in ("2022-01-01", "2023-01-01", "2024-01-01"):
        mask = development.masks()["development_all"] & (development.dates >= pd.Timestamp(start))
        starts[start] = metrics(
            selected["streams"][0].values[mask],
            selected["streams"][0].benchmark[mask],
            selected["streams"][0].active[mask],
        )
    neighbors = [cell for cell in cells if abs(cell["state_index"] - selected["state_index"]) <= 1]
    neighbor_share = sum(
        all(_primary(observation) for observation in cell["observations"]) for cell in neighbors
    ) / len(neighbors)
    oos = standard["development_oos_2024_2025"]
    z_score = float(oos["information_ratio"]) * math.sqrt(max(1, int(oos["trades"])) / 252)
    bonferroni = min(1.0, 2.0 * prior.v47._normal_tail(abs(z_score)) * cumulative_cells)
    gates = {
        "standard_primary": _primary(standard),
        "cost_18bp_primary": _primary(cost),
        "delay_5min_primary": _primary(delay),
        "four_of_five_positive_folds": sum(
            float(observation["annualized_return"]) > 0 for observation in folds
        )
        >= 4,
        "historical_positive_mdd_below_20pct": (
            float(historical_obs["annualized_return"]) > 0
            and float(historical_obs["max_drawdown"]) < 0.20
        ),
        "parameter_neighborhood_70pct_primary": neighbor_share >= 0.70,
        "consumed_2026q1_above_5pct": float(standard["consumed_2026q1"]["total_return"])
        > 0.05,
        "consumed_2026_all_above_5pct": float(standard["consumed_2026_all"]["total_return"])
        > 0.05,
        "cumulative_bonferroni_5pct": bonferroni < 0.05,
    }
    pre_null = all(passed for name, passed in gates.items() if name != "cumulative_bonferroni_5pct")
    definition = {"version": version, **selected["definition"]}
    return {
        "candidate_id": f"lev-v{version}-" + prior._identity(definition),
        "definition": definition,
        "development_rank": list(selected["rank"]),
        "standard": standard,
        "cost_18bp": cost,
        "delay_5min_9bp": delay,
        "historical_2018_2020": historical_obs,
        "development_folds": folds,
        "start_date_stress": starts,
        "neighbor_primary_share": neighbor_share,
        "multiple_comparison": {
            "cumulative_cells": cumulative_cells,
            "z_score": z_score,
            "bonferroni_p": bonferroni,
        },
        "gates": gates,
        "pre_factory_null_pass": pre_null,
        "all_reference_gates_pass": all(gates.values()),
    }


def _failures(records: list[dict]) -> Counter[str]:
    return Counter(
        name for record in records for name, passed in record["gates"].items() if not passed
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    development = prior.v53.Cube(args.root, "alpaca", 0)
    historical = prior.v53.Cube(args.root, "historical", 0)
    models = prior.v44._fit(development, (20, 23, 26, 29), 72)
    anchor_development = anchored._v45_streams(development, models)
    anchor_historical = anchored._v45_streams(historical, models)[0]
    component_records = {
        name: _component_record(args.source_dir, candidate_id)
        for name, candidate_id in COMPONENT_IDS.items()
    }
    component_development = {
        name: anchored._component_streams(development, record)
        for name, record in component_records.items()
    }
    component_historical = {
        name: anchored._component_streams(historical, record)[0]
        for name, record in component_records.items()
    }
    specifications = list(itertools.product(ROUTING_MODES, TOTAL_WEIGHTS, V247_SHARES))
    if len(specifications) != 100:
        raise RuntimeError("V753_V852_VERSION_COUNT_MISMATCH")
    planned_cells = sum(1 if mode[1] is None else len(STATE_QUANTILES) for mode, _, _ in specifications)
    cumulative_cells = PRIOR_COMPARISON_CELLS + planned_cells
    all_records: list[dict] = []
    versions = []
    for offset, (mode, total_weight, v247_share) in enumerate(specifications):
        version = FIRST_VERSION + offset
        path = args.output_dir / f"full-universe-intraday-v{version}-exact.json"
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            records = payload["records"]
        else:
            name, clock, coefficients = mode
            state_options = _state_allowed(development, historical, clock, coefficients)
            cells = []
            for state_index, (threshold, dev_allowed, hist_allowed) in enumerate(state_options):
                streams = tuple(
                    _blend(
                        _route(anchor, dev_allowed) if ROUTE_ANCHOR else anchor,
                        _route(v247, dev_allowed),
                        _route(v449, dev_allowed),
                        total_weight=total_weight,
                        v247_share=v247_share,
                        allowed=dev_allowed,
                    )
                    for anchor, v247, v449 in zip(
                        anchor_development,
                        component_development["v247"],
                        component_development["v449"],
                        strict=True,
                    )
                )
                historical_stream = _blend(
                    _route(anchor_historical, hist_allowed)
                    if ROUTE_ANCHOR
                    else anchor_historical,
                    _route(component_historical["v247"], hist_allowed),
                    _route(component_historical["v449"], hist_allowed),
                    total_weight=total_weight,
                    v247_share=v247_share,
                    allowed=hist_allowed,
                )
                observations = tuple(
                    prior.v47._observe(development, stream, True) for stream in streams
                )
                definition = {
                    "routing_mode": name,
                    "state_clock": clock,
                    "state_coefficients": coefficients,
                    "state_quantile": None if threshold is None else STATE_QUANTILES[state_index],
                    "state_threshold": threshold,
                    "anchor_candidate_id": "lev-v45e-0d302fbf92727a31",
                    "anchor_weight": 1.0 - total_weight,
                    **({"anchor_state_routed": True} if ROUTE_ANCHOR else {}),
                    **(
                        {"blocked_component_reallocation": "anchor"}
                        if REALLOCATE_TO_ANCHOR_WHEN_BLOCKED
                        else {}
                    ),
                    **({"development_rank_mode": RANK_MODE} if RANK_MODE != "legacy" else {}),
                    "v247_component_id": COMPONENT_IDS["v247"],
                    "v247_component_weight": total_weight * v247_share,
                    "v449_component_id": COMPONENT_IDS["v449"],
                    "v449_component_weight": total_weight * (1.0 - v247_share),
                    "maximum_gross": 1.0,
                }
                cells.append(
                    {
                        "definition": definition,
                        "state_index": state_index,
                        "streams": streams,
                        "historical_stream": historical_stream,
                        "observations": observations,
                        "rank": _rank(observations),
                    }
                )
            cells.sort(key=lambda item: item["rank"], reverse=True)
            records = [
                _record(development, historical, version, cells, cell, cumulative_cells)
                for cell in cells[: min(3, len(cells))]
            ]
            payload = {
                "schema_version": "1.0.0",
                "status": "COMPLETE",
                "version": version,
                "economic_hypothesis": (
                    f"{name}: component_total={total_weight:.2f}, v247_share={v247_share:.2f}"
                ),
                "scan": {
                    "evaluated_cells": len(cells),
                    "frozen_frontier": len(records),
                    "elapsed_seconds": time.perf_counter() - started,
                },
                "pre_factory_null_hits": sum(record["pre_factory_null_pass"] for record in records),
                "records": records,
            }
            _atomic(path, payload)
        all_records.extend(records)
        versions.append(
            {
                "version": version,
                "hypothesis": payload["economic_hypothesis"],
                "cells": payload["scan"]["evaluated_cells"],
                "pre_factory_null_hits": payload["pre_factory_null_hits"],
                "best_candidate_id": records[0]["candidate_id"],
                "best_oos_annualized_return": records[0]["standard"]["development_oos_2024_2025"][
                    "annualized_return"
                ],
                "best_consumed_2026q1_total_return": records[0]["standard"]["consumed_2026q1"][
                    "total_return"
                ],
                "best_consumed_2026_total_return": records[0]["standard"]["consumed_2026_all"][
                    "total_return"
                ],
            }
        )
        summary = {
            "schema_version": "1.0.0",
            "status": "COMPLETE" if version == LAST_VERSION else "RUNNING",
            "version_range": [FIRST_VERSION, LAST_VERSION],
            "planned_versions": 100,
            "completed_versions": offset + 1,
            "planned_new_cells": planned_cells,
            "cumulative_comparison_cells": cumulative_cells,
            "pre_factory_null_hits": sum(record["pre_factory_null_pass"] for record in all_records),
            "rejected_frontier_records": len(all_records)
            - sum(record["pre_factory_null_pass"] for record in all_records),
            "rejection_reason_counts": dict(_failures(all_records)),
            "elapsed_seconds": time.perf_counter() - started,
            "versions": versions,
        }
        _atomic(args.summary, summary)
        print(json.dumps({"progress": f"{offset + 1}/100", **versions[-1]}), flush=True)


if __name__ == "__main__":
    main()
