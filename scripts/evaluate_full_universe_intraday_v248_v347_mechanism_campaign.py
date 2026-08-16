"""v248-v347: fifty v45 state enhancements and fifty independent rule versions."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from pathlib import Path

import analyze_full_universe_intraday_v53_cross_asset_factors as v53
import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v42_multifactor_vol_target as v42
import evaluate_full_universe_intraday_v44_multihorizon_confirmation as v44
import evaluate_full_universe_intraday_v45_event_trigger_multifactor as v45
import evaluate_full_universe_intraday_v47_score_slope as v47
import numpy as np
import pandas as pd
import search_full_universe_intraday_v12_robustness as v12
import search_full_universe_intraday_v13_regime_rotation as v13

from us_intraday_lab.fast_intraday_research import metrics

ASSETS = np.array((3, 4))
STATE_QUANTILES = (0.30, 0.40, 0.50, 0.60, 0.70)
RULE_QUANTILES = (0.40, 0.50, 0.60, 0.70)
TARGETS = (0.25, 0.30, 0.35)
LOOKBACKS = (15, 25)
CONFIRMATIONS = (1, 2)
PRIOR_COMPARISON_CELLS = 28_860

STATE_BASES = (
    "spy_current",
    "qqq_current",
    "iwm_current",
    "qqq_minus_iwm",
    "sector_breadth",
    "sector_dispersion",
    "cyclical_minus_defensive",
    "tech_minus_market",
    "risk_asset_agreement",
    "spy_volatility",
)
STATE_CONCEPTS = tuple(
    [(f"{name}_high", {name: 1.0}) for name in STATE_BASES]
    + [(f"{name}_low", {name: -1.0}) for name in STATE_BASES]
    + [
        ("broad_risk_on", {"spy_current": 1.0, "sector_breadth": 1.0}),
        ("technology_leadership", {"qqq_minus_iwm": 1.0, "tech_minus_market": 1.0}),
        ("calm_trend", {"spy_current": 1.0, "spy_volatility": -1.0}),
        (
            "broad_cyclical",
            {"sector_breadth": 1.0, "cyclical_minus_defensive": 1.0},
        ),
        (
            "agreement_low_dispersion",
            {"risk_asset_agreement": 1.0, "sector_dispersion": -1.0},
        ),
    ]
)
STATE_CLOCKS = ("bar17", "prior_close")

RULE_FAMILIES = (
    ("relative_strength", ("current_return", "recent_return", "relative_return"), (1, 1, 1)),
    (
        "flow_persistence",
        ("current_return", "signed_volume_imbalance", "volume_acceleration"),
        (1, 1, -1),
    ),
    (
        "efficient_breakout",
        ("current_return", "path_efficiency", "close_location"),
        (1, 1, 1),
    ),
    (
        "vwap_reclaim",
        ("recent_return", "vwap_distance", "close_location"),
        (1, 1, 1),
    ),
    (
        "low_vol_breakout",
        ("current_return", "path_efficiency", "realized_volatility"),
        (1, 1, -1),
    ),
    (
        "residual_momentum",
        ("leverage_residual", "current_rank", "relative_return"),
        (1, 1, 1),
    ),
    (
        "prior_weak_reversal",
        ("prior20_return", "recent_return", "close_location"),
        (-1, 1, 1),
    ),
    ("gap_follow", ("gap", "current_return", "relative_return"), (1, 1, 1)),
    (
        "rank_rotation",
        ("current_rank", "prior20_rank", "relative_return"),
        (1, -1, 1),
    ),
    (
        "balanced_confirmation",
        (
            "current_return",
            "relative_return",
            "path_efficiency",
            "signed_volume_imbalance",
            "close_location",
        ),
        (1, 1, 1, 1, 1),
    ),
)
RULE_SCHEDULES = ((8, 23), (17, 36), (23, 47), (29, 56), (41, 72))


def _identity(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()[:16]


def _primary_triplet(observations: tuple[dict, dict, dict]) -> bool:
    return all(v13._primary(item) for item in observations)


def _mask_stream(stream: v12.ReturnStream, allowed: np.ndarray) -> v12.ReturnStream:
    active = stream.active & allowed
    return v12.ReturnStream(
        np.where(active, stream.values, 0.0),
        np.where(active, stream.benchmark, 0.0),
        active,
        np.where(active, stream.component_trades, 0),
    )


def _state_matrix(cube: v53.Cube, clock: str) -> dict[str, np.ndarray]:
    decision = 17 if clock == "bar17" else 77
    factors = cube.factors(decision)
    values = {name: np.asarray(factors[name][:, 0], dtype=float) for name in STATE_BASES}
    if clock == "prior_close":
        values = {
            name: np.concatenate((np.array([np.nan]), value[:-1])) for name, value in values.items()
        }
    return values


def _state_score(
    matrix: dict[str, np.ndarray],
    coefficients: dict[str, float],
    means: dict[str, float],
    scales: dict[str, float],
) -> np.ndarray:
    pieces = [
        direction * (matrix[name] - means[name]) / scales[name]
        for name, direction in coefficients.items()
    ]
    return np.mean(np.stack(pieces, axis=1), axis=1)


def _state_cells(
    development: v53.Cube,
    historical: v53.Cube,
    anchor_development: tuple[v12.ReturnStream, ...],
    anchor_historical: v12.ReturnStream,
    concept: tuple[str, dict[str, float]],
    clock: str,
) -> list[dict]:
    name, coefficients = concept
    train = development.masks()["train_2022_2023"]
    dev_matrix = _state_matrix(development, clock)
    hist_matrix = _state_matrix(historical, clock)
    means = {
        factor: float(np.nanmean(values[train]))
        for factor, values in dev_matrix.items()
        if factor in coefficients
    }
    scales = {
        factor: max(1e-8, float(np.nanstd(dev_matrix[factor][train]))) for factor in coefficients
    }
    dev_score = _state_score(dev_matrix, coefficients, means, scales)
    hist_score = _state_score(hist_matrix, coefficients, means, scales)
    finite_train = dev_score[train & np.isfinite(dev_score)]
    cells = []
    for quantile in STATE_QUANTILES:
        threshold = float(np.quantile(finite_train, quantile))
        streams = tuple(
            _mask_stream(stream, np.isfinite(dev_score) & (dev_score >= threshold))
            for stream in anchor_development
        )
        historical_stream = _mask_stream(
            anchor_historical,
            np.isfinite(hist_score) & (hist_score >= threshold),
        )
        observations = tuple(v47._observe(development, stream, True) for stream in streams)
        cells.append(
            {
                "parameters": {"quantile": quantile, "threshold": threshold},
                "streams": streams,
                "historical_stream": historical_stream,
                "observations": observations,
                "rank": v47._rank(*observations),
                "primary": _primary_triplet(observations),
                "mechanism": name,
                "clock": clock,
            }
        )
    return cells


def _fit_rule_stats(
    cube: v53.Cube, decision: int, factors: tuple[str, ...]
) -> tuple[np.ndarray, np.ndarray]:
    available = cube.factors(decision)
    matrix = np.stack([available[name][:, ASSETS] for name in factors], axis=2)
    selected = matrix[cube.masks()["train_2022_2023"]]
    values = selected.reshape(-1, len(factors))
    values = values[np.isfinite(values).all(axis=1)]
    mean = values.mean(axis=0)
    scale = values.std(axis=0)
    scale[scale < 1e-8] = 1.0
    return mean, scale


def _rule_score(
    cube: v53.Cube,
    decision: int,
    factors: tuple[str, ...],
    directions: tuple[int, ...],
    mean: np.ndarray,
    scale: np.ndarray,
) -> np.ndarray:
    available = cube.factors(decision)
    matrix = np.stack([available[name][:, ASSETS] for name in factors], axis=2)
    score = np.mean((matrix - mean) / scale * np.asarray(directions), axis=2)
    return np.where(np.isfinite(matrix).all(axis=2), score, -np.inf)


def _rule_raw(
    cube: v53.Cube,
    definition: dict,
    mean: np.ndarray,
    scale: np.ndarray,
    threshold: float,
    cost: float,
    delay: int,
) -> v12.ReturnStream:
    decision = int(definition["decision"])
    exit_bar = int(definition["exit"])
    factors = tuple(definition["factors"])
    directions = tuple(int(value) for value in definition["directions"])
    score = _rule_score(cube, decision, factors, directions, mean, scale)
    local = np.argmax(score, axis=1)
    selected = ASSETS[local]
    best = score[cube.rows, local]
    active = np.isfinite(best) & (best >= threshold)
    if int(definition["confirmations"]) == 2:
        earlier = _rule_score(cube, decision - 3, factors, directions, mean, scale)
        earlier_local = np.argmax(earlier, axis=1)
        earlier_best = earlier[cube.rows, earlier_local]
        active &= (
            (ASSETS[earlier_local] == selected)
            & np.isfinite(earlier_best)
            & (earlier_best >= threshold)
        )
    entry = decision + 1 + delay
    active &= cube.first[cube.rows, entry, selected] <= entry * 5 + cube.boundary_tolerance
    active &= cube.first[cube.rows, exit_bar, selected] <= exit_bar * 5 + cube.boundary_tolerance
    active &= np.isfinite(cube.opens[cube.rows, entry, selected])
    active &= np.isfinite(cube.opens[cube.rows, exit_bar, selected])
    active &= np.isfinite(cube.opens[:, entry, 0])
    active &= np.isfinite(cube.opens[:, exit_bar, 0])
    active &= cube.opens[cube.rows, entry, selected] > 0
    active &= cube.opens[:, entry, 0] > 0
    values = np.zeros(len(cube.sessions))
    values[active] = (
        cube.opens[active, exit_bar, selected[active]] / cube.opens[active, entry, selected[active]]
        - 1.0
        - cost
    )
    benchmark = np.zeros(len(cube.sessions))
    benchmark[active] = cube.opens[active, exit_bar, 0] / cube.opens[active, entry, 0] - 1.0
    return v12.ReturnStream(values, benchmark, active, active.astype(int))


def _rule_streams(
    cube: v53.Cube,
    definition: dict,
    mean: np.ndarray,
    scale: np.ndarray,
    threshold: float,
) -> tuple[v12.ReturnStream, ...]:
    raw = (
        _rule_raw(cube, definition, mean, scale, threshold, v34.STANDARD_COST, 0),
        _rule_raw(cube, definition, mean, scale, threshold, v34.STRESS_COST, 0),
        _rule_raw(cube, definition, mean, scale, threshold, v34.STANDARD_COST, 1),
    )
    exposure = v42._exposure(
        raw[0].values,
        int(definition["lookback"]),
        float(definition["target_volatility"]),
        0.0,
    )
    return tuple(v42._scaled(stream, exposure) for stream in raw)


def _rule_cells(
    development: v53.Cube,
    historical: v53.Cube,
    family: tuple[str, tuple[str, ...], tuple[int, ...]],
    schedule: tuple[int, int],
) -> list[dict]:
    name, factors, directions = family
    decision, exit_bar = schedule
    mean, scale = _fit_rule_stats(development, decision, factors)
    base_definition = {
        "mechanism": name,
        "decision": decision,
        "exit": exit_bar,
        "factors": factors,
        "directions": directions,
    }
    train_score = _rule_score(development, decision, factors, directions, mean, scale)
    best = np.max(train_score, axis=1)
    train = development.masks()["train_2022_2023"]
    threshold_values = best[train & np.isfinite(best)]
    cells = []
    for quantile in RULE_QUANTILES:
        threshold = float(np.quantile(threshold_values, quantile))
        for confirmations in CONFIRMATIONS:
            for target in TARGETS:
                for lookback in LOOKBACKS:
                    definition = {
                        **base_definition,
                        "threshold_quantile": quantile,
                        "score_threshold": threshold,
                        "confirmations": confirmations,
                        "target_volatility": target,
                        "lookback": lookback,
                    }
                    streams = _rule_streams(development, definition, mean, scale, threshold)
                    historical_stream = _rule_streams(
                        historical, definition, mean, scale, threshold
                    )[0]
                    observations = tuple(
                        v47._observe(development, stream, True) for stream in streams
                    )
                    cells.append(
                        {
                            "parameters": definition,
                            "model": {"mean": mean.tolist(), "scale": scale.tolist()},
                            "streams": streams,
                            "historical_stream": historical_stream,
                            "observations": observations,
                            "rank": v47._rank(*observations),
                            "primary": _primary_triplet(observations),
                        }
                    )
    return cells


def _neighbor_share(cells: list[dict], selected: dict, kind: str) -> float:
    if kind == "state":
        position = STATE_QUANTILES.index(float(selected["parameters"]["quantile"]))
        quantiles = STATE_QUANTILES[max(0, position - 1) : position + 2]
        neighbors = [cell for cell in cells if cell["parameters"]["quantile"] in quantiles]
    else:
        selected_parameters = selected["parameters"]
        indexes = (
            RULE_QUANTILES.index(float(selected_parameters["threshold_quantile"])),
            CONFIRMATIONS.index(int(selected_parameters["confirmations"])),
            TARGETS.index(float(selected_parameters["target_volatility"])),
            LOOKBACKS.index(int(selected_parameters["lookback"])),
        )
        neighbors = []
        for cell in cells:
            parameters = cell["parameters"]
            candidate = (
                RULE_QUANTILES.index(float(parameters["threshold_quantile"])),
                CONFIRMATIONS.index(int(parameters["confirmations"])),
                TARGETS.index(float(parameters["target_volatility"])),
                LOOKBACKS.index(int(parameters["lookback"])),
            )
            if sum(abs(left - right) for left, right in zip(indexes, candidate, strict=True)) <= 1:
                neighbors.append(cell)
    return sum(cell["primary"] for cell in neighbors) / len(neighbors)


def _record(
    development: v53.Cube,
    historical: v53.Cube,
    version: int,
    kind: str,
    cells: list[dict],
    selected: dict,
    total_cells: int,
) -> dict:
    standard, cost, delay = selected["observations"]
    historical_observation = v47._observe(historical, selected["historical_stream"], True)[
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
    neighborhood = _neighbor_share(cells, selected, kind)
    oos = standard["development_oos_2024_2025"]
    z_score = float(oos["information_ratio"]) * math.sqrt(max(1, int(oos["trades"])) / 252)
    bonferroni = min(1.0, 2.0 * v47._normal_tail(abs(z_score)) * total_cells)
    gates = {
        "standard_primary": v13._primary(standard),
        "cost_18bp_primary": v13._primary(cost),
        "delay_5min_primary": v13._primary(delay),
        "four_of_five_positive_folds": (
            sum(float(item["annualized_return"]) > 0 for item in folds) >= 4
        ),
        "historical_positive_mdd_below_20pct": (
            float(historical_observation["annualized_return"]) > 0
            and float(historical_observation["max_drawdown"]) < 0.20
        ),
        "parameter_neighborhood_70pct_primary": neighborhood >= 0.70,
        "consumed_2026_total_above_5pct": (
            float(standard["consumed_2026_all"]["total_return"]) > 0.05
        ),
        "cumulative_bonferroni_5pct": bonferroni < 0.05,
    }
    pre_null_names = tuple(name for name in gates if name != "cumulative_bonferroni_5pct")
    definition = {
        "version": version,
        "kind": kind,
        **selected["parameters"],
    }
    if kind == "state":
        definition.update({"mechanism": selected["mechanism"], "clock": selected["clock"]})
    return {
        "candidate_id": f"lev-v{version}-" + _identity(definition),
        "definition": definition,
        "model": selected.get("model"),
        "development_rank": list(selected["rank"]),
        "standard": standard,
        "cost_18bp": cost,
        "delay_5min_9bp": delay,
        "historical_2018_2020": historical_observation,
        "development_folds": folds,
        "start_date_stress": starts,
        "neighbor_primary_share": neighborhood,
        "multiple_comparison": {
            "total_cells": total_cells,
            "z_score": z_score,
            "bonferroni_p": bonferroni,
        },
        "gates": gates,
        "pre_factory_null_pass": all(gates[name] for name in pre_null_names),
        "all_reference_gates_pass": all(gates.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    development = v53.Cube(args.root, "alpaca", 0)
    historical = v53.Cube(args.root, "historical", 0)
    anchor_models = v44._fit(development, (20, 23, 26, 29), 72)
    anchor_development = (
        v42._scaled(
            stream,
            v42._exposure(
                v45._stream(
                    development,
                    anchor_models,
                    72,
                    "reliability",
                    0.75,
                    2,
                    v34.STANDARD_COST,
                    0,
                ).values,
                15,
                0.35,
                0.0,
            ),
        )
        for stream in (
            v45._stream(development, anchor_models, 72, "reliability", 0.75, 2, cost, delay)
            for cost, delay in (
                (v34.STANDARD_COST, 0),
                (v34.STRESS_COST, 0),
                (v34.STANDARD_COST, 1),
            )
        )
    )
    anchor_development = tuple(anchor_development)
    historical_anchor_raw = v45._stream(
        historical, anchor_models, 72, "reliability", 0.75, 2, v34.STANDARD_COST, 0
    )
    anchor_historical = v42._scaled(
        historical_anchor_raw,
        v42._exposure(historical_anchor_raw.values, 15, 0.35, 0.0),
    )
    planned_new_cells = len(STATE_CONCEPTS) * len(STATE_CLOCKS) * len(STATE_QUANTILES) + (
        len(RULE_FAMILIES)
        * len(RULE_SCHEDULES)
        * len(RULE_QUANTILES)
        * len(CONFIRMATIONS)
        * len(TARGETS)
        * len(LOOKBACKS)
    )
    total_cells = PRIOR_COMPARISON_CELLS + planned_new_cells
    versions = []
    total_pre_null = 0
    total_reference = 0
    specifications = [
        ("state", concept, clock) for clock in STATE_CLOCKS for concept in STATE_CONCEPTS
    ] + [("rule", family, schedule) for schedule in RULE_SCHEDULES for family in RULE_FAMILIES]
    if len(specifications) != 100:
        raise RuntimeError("campaign must contain exactly 100 independent versions")
    for offset, specification in enumerate(specifications):
        version = 248 + offset
        version_started = time.perf_counter()
        kind = str(specification[0])
        if kind == "state":
            cells = _state_cells(
                development,
                historical,
                anchor_development,
                anchor_historical,
                specification[1],
                str(specification[2]),
            )
        else:
            cells = _rule_cells(
                development,
                historical,
                specification[1],
                specification[2],
            )
        cells.sort(key=lambda item: item["rank"], reverse=True)
        records = [
            _record(development, historical, version, kind, cells, cell, total_cells)
            for cell in cells[:3]
        ]
        pre_null = sum(record["pre_factory_null_pass"] for record in records)
        reference = sum(record["all_reference_gates_pass"] for record in records)
        total_pre_null += pre_null
        total_reference += reference
        payload = {
            "schema_version": "1.0.0",
            "status": "COMPLETE",
            "version": version,
            "selection_contract": (
                "rank and tune on 2022-2025 only; attach separate historical and consumed-2026 "
                "after the three-record frontier freezes"
            ),
            "scan": {
                "evaluated_cells": len(cells),
                "frozen_frontier": len(records),
                "elapsed_seconds": time.perf_counter() - version_started,
            },
            "pre_factory_null_hits": pre_null,
            "all_reference_gate_hits": reference,
            "records": records,
        }
        v12._atomic(args.output_dir / f"full-universe-intraday-v{version}-exact.json", payload)
        versions.append(
            {
                "version": version,
                "kind": kind,
                "cells": len(cells),
                "pre_factory_null_hits": pre_null,
                "all_reference_gate_hits": reference,
                "best_candidate_id": records[0]["candidate_id"],
                "best_oos_annualized_return": records[0]["standard"]["development_oos_2024_2025"][
                    "annualized_return"
                ],
                "best_consumed_2026_total_return": records[0]["standard"]["consumed_2026_all"][
                    "total_return"
                ],
            }
        )
        v12._atomic(
            args.summary,
            {
                "schema_version": "1.0.0",
                "status": "RUNNING" if offset < 99 else "COMPLETE",
                "version_range": [248, 347],
                "planned_versions": 100,
                "completed_versions": offset + 1,
                "planned_new_cells": planned_new_cells,
                "cumulative_comparison_cells": total_cells,
                "pre_factory_null_hits": total_pre_null,
                "all_reference_gate_hits": total_reference,
                "elapsed_seconds": time.perf_counter() - started,
                "versions": versions,
            },
        )
        print(
            json.dumps(
                {
                    "progress": f"{offset + 1}/100",
                    "version": version,
                    "kind": kind,
                    "pre_factory_null_hits": pre_null,
                    "total_pre_factory_null_hits": total_pre_null,
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
