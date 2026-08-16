"""One-hundred predeclared multi-factor rounds with global selection pressure."""

from __future__ import annotations

import argparse
import itertools
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path

import analyze_full_universe_intraday_v53_cross_asset_factors as v53
import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v35_rank_ensemble as v35
import evaluate_full_universe_intraday_v42_multifactor_vol_target as v42
import evaluate_full_universe_intraday_v47_score_slope as v47
import numpy as np
import search_full_universe_intraday_v12_robustness as v12
import search_full_universe_intraday_v13_regime_rotation as v13

from us_intraday_lab.fast_intraday_research import metrics

ASSETS = np.array((3, 4))
TIMINGS = ((17, 47), (23, 65), (29, 72), (35, 69), (41, 75))
WEIGHTINGS = ("equal", "reliability")
THRESHOLDS = (0.0, 0.25, 0.50, 0.75, 1.0)
TARGETS = (0.25, 0.30, 0.35)
LOOKBACKS = (15, 20)
TOP_PER_ROUND = 5
WEAK_MARKET_2026_MIN_TOTAL_RETURN = 0.05

TEMPLATES = {
    "trend_quality": (
        "current_return",
        "relative_return",
        "path_efficiency",
        "trend_consistency",
        "close_location",
    ),
    "flow_persistence": (
        "current_return",
        "recent_return",
        "signed_volume_imbalance",
        "volume_acceleration",
        "path_efficiency",
    ),
    "relative_rotation": (
        "relative_return",
        "current_rank",
        "prior20_rank",
        "prior20_return",
        "sector_breadth",
    ),
    "reclaim_state": (
        "recent_return",
        "vwap_distance",
        "close_location",
        "prior1_return",
        "spy_prior20",
    ),
    "volatility_breakout": (
        "current_return",
        "path_efficiency",
        "realized_volatility",
        "session_range",
        "range_ratio",
    ),
    "prior_reversal": (
        "current_return",
        "recent_return",
        "prior1_return",
        "prior20_return",
        "prior20_rank",
    ),
    "market_confirmation": (
        "current_return",
        "relative_return",
        "spy_current",
        "qqq_current",
        "risk_asset_agreement",
    ),
    "sector_confirmation": (
        "current_return",
        "sector_breadth",
        "cyclical_minus_defensive",
        "tech_minus_market",
        "current_rank",
    ),
    "dispersion_breakout": (
        "relative_return",
        "sector_dispersion",
        "sector_breadth",
        "session_range",
        "path_efficiency",
    ),
    "leverage_mean_reversion": (
        "leverage_residual",
        "recent_return",
        "vwap_distance",
        "prior20_return",
        "volume_acceleration",
    ),
    "breadth_cash": (
        "sector_breadth",
        "risk_asset_agreement",
        "spy_current",
        "spy_volatility",
        "sector_dispersion",
    ),
    "tech_leadership": (
        "tech_minus_market",
        "qqq_minus_iwm",
        "qqq_current",
        "relative_return",
        "current_rank",
    ),
    "cyclical_risk": (
        "cyclical_minus_defensive",
        "iwm_current",
        "risk_asset_agreement",
        "sector_breadth",
        "prior20_return",
    ),
    "gap_continuation": (
        "gap",
        "current_return",
        "trend_consistency",
        "signed_volume_imbalance",
        "spy_current",
    ),
    "gap_reversal": (
        "gap",
        "recent_return",
        "vwap_distance",
        "close_location",
        "volume_acceleration",
    ),
    "low_vol_momentum": (
        "current_return",
        "relative_return",
        "path_efficiency",
        "realized_volatility",
        "spy_volatility",
    ),
    "quality_reclaim": (
        "recent_return",
        "path_efficiency",
        "vwap_distance",
        "close_location",
        "range_ratio",
        "prior1_return",
    ),
    "cross_state_rotation": (
        "current_rank",
        "prior20_rank",
        "qqq_minus_iwm",
        "tech_minus_market",
        "sector_breadth",
        "spy_prior20",
    ),
    "volume_dryup": (
        "volume_acceleration",
        "signed_volume_imbalance",
        "realized_volatility",
        "range_ratio",
        "recent_return",
    ),
    "balanced": (
        "current_return",
        "recent_return",
        "path_efficiency",
        "volume_acceleration",
        "vwap_distance",
        "prior20_return",
        "sector_breadth",
        "tech_minus_market",
    ),
}


@dataclass(slots=True)
class Model:
    factors: tuple[str, ...]
    decision: int
    exit_bar: int
    mean: np.ndarray
    scale: np.ndarray
    direction: np.ndarray
    reliability: np.ndarray


def _fit(cube: v53.Cube, factors: tuple[str, ...], decision: int, exit_bar: int) -> Model | None:
    specification = {"decision": decision, "exit": exit_bar, "assets": ASSETS}
    matrix, label, finite = v34._matrix(cube, specification, factors)
    selected = cube.masks()["train_2022_2023"][:, None] & finite
    values = matrix[selected]
    target = label[selected]
    if len(target) < 100:
        return None
    mean = values.mean(axis=0)
    scale = values.std(axis=0)
    scale[scale < 1e-8] = 1.0
    direction = np.ones(len(factors))
    reliability = np.zeros(len(factors))
    for index in range(len(factors)):
        ic = v35._spearman(values[:, index], target)
        if not np.isfinite(ic):
            return None
        direction[index] = 1.0 if ic >= 0 else -1.0
        reliability[index] = max(abs(ic), 0.002)
    return Model(factors, decision, exit_bar, mean, scale, direction, reliability)


def _stream(cube: v53.Cube, model: Model, definition: dict, cost: float, delay: int):
    specification = {"decision": model.decision, "exit": model.exit_bar, "assets": ASSETS}
    matrix, _, _ = v34._matrix(cube, specification, model.factors)
    weights = model.reliability.copy()
    if definition["weighting"] == "equal":
        weights[:] = 1.0
    weights /= weights.sum()
    score = np.einsum("saf,f,f->sa", (matrix - model.mean) / model.scale, model.direction, weights)
    score = np.where(np.isfinite(matrix).all(axis=2), score, -np.inf)
    local = np.argmax(score, axis=1)
    selected = ASSETS[local]
    best = score[cube.rows, local]
    entry = model.decision + 1 + delay
    active = np.isfinite(best) & (best >= float(definition["score_threshold"]))
    active &= cube.first[cube.rows, entry, selected] <= entry * 5 + cube.boundary_tolerance
    active &= (
        cube.first[cube.rows, model.exit_bar, selected]
        <= model.exit_bar * 5 + cube.boundary_tolerance
    )
    active &= np.isfinite(cube.opens[cube.rows, entry, selected])
    active &= np.isfinite(cube.opens[cube.rows, model.exit_bar, selected])
    active &= np.isfinite(cube.opens[:, entry, 0])
    active &= np.isfinite(cube.opens[:, model.exit_bar, 0])
    active &= cube.opens[cube.rows, entry, selected] > 0
    active &= cube.opens[:, entry, 0] > 0
    values = np.zeros(len(cube.sessions))
    values[active] = (
        cube.opens[active, model.exit_bar, selected[active]]
        / cube.opens[active, entry, selected[active]]
        - 1.0
        - cost
    )
    benchmark = np.zeros(len(cube.sessions))
    benchmark[active] = cube.opens[active, model.exit_bar, 0] / cube.opens[active, entry, 0] - 1.0
    raw = v12.ReturnStream(values, benchmark, active, active.astype(int))
    exposure = v42._exposure(
        raw.values, int(definition["lookback"]), float(definition["target_volatility"]), 0.0
    )
    return v42._scaled(raw, exposure)


def _definition(round_id: int, template: str, model: Model, values: tuple) -> dict:
    weighting, threshold, target, lookback = values
    return {
        "round": round_id,
        "template": template,
        "factors": model.factors,
        "decision": model.decision,
        "exit": model.exit_bar,
        "weighting": weighting,
        "score_threshold": threshold,
        "target_volatility": target,
        "lookback": lookback,
    }


def _neighbor_share(definition: dict, round_records: list[dict]) -> float:
    varying = ("weighting", "score_threshold", "target_volatility", "lookback")
    neighbors = []
    for item in round_records:
        other = item["definition"]
        differences = sum(other[name] != definition[name] for name in varying)
        if differences == 1:
            neighbors.append(item)
    if not neighbors:
        return 0.0
    passing = sum(
        float(item["standard_development"]["development_oos_2024_2025"]["annualized_return"]) > 0
        for item in neighbors
    )
    return passing / len(neighbors)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if len(TEMPLATES) != 20 or len(TIMINGS) != 5:
        raise RuntimeError("v57 contract requires exactly 100 factor-timing rounds")
    started = time.perf_counter()
    development = v53.Cube(args.root, "alpaca", 0)
    historical = v53.Cube(args.root, "historical", 0)
    planned = (
        len(TEMPLATES)
        * len(TIMINGS)
        * len(WEIGHTINGS)
        * len(THRESHOLDS)
        * len(TARGETS)
        * len(LOOKBACKS)
    )
    rounds = []
    frontier = []
    round_id = 0
    for template, factors in TEMPLATES.items():
        for decision, exit_bar in TIMINGS:
            round_id += 1
            model = _fit(development, factors, decision, exit_bar)
            if model is None:
                rounds.append({"round": round_id, "template": template, "status": "FIT_REJECTED"})
                continue
            cells = []
            for values in itertools.product(WEIGHTINGS, THRESHOLDS, TARGETS, LOOKBACKS):
                definition = _definition(round_id, template, model, values)
                streams = (
                    _stream(development, model, definition, v34.STANDARD_COST, 0),
                    _stream(development, model, definition, v34.STRESS_COST, 0),
                    _stream(development, model, definition, v34.STANDARD_COST, 1),
                )
                observations = [v47._observe(development, stream) for stream in streams]
                cells.append(
                    {
                        "definition": definition,
                        "model": model,
                        "streams": streams,
                        "observations": observations,
                        "standard_development": observations[0],
                        "rank": v47._rank(*observations),
                    }
                )
            cells.sort(key=lambda item: item["rank"], reverse=True)
            rounds.append(
                {
                    "round": round_id,
                    "template": template,
                    "decision": decision,
                    "exit": exit_bar,
                    "status": "COMPLETE",
                    "evaluated_cells": len(cells),
                    "best_rank": list(cells[0]["rank"]),
                }
            )
            for item in cells[:TOP_PER_ROUND]:
                item["neighbor_positive_share"] = _neighbor_share(item["definition"], cells)
                frontier.append(item)
    frontier.sort(key=lambda item: item["rank"], reverse=True)
    folds = np.array_split(np.flatnonzero(development.masks()["development_all"]), 5)
    records = []
    pre_null_hits = 0
    for item in frontier:
        definition = item["definition"]
        model = item["model"]
        streams = item["streams"]
        standard, cost, delay = [v47._observe(development, stream, True) for stream in streams]
        historical_stream = _stream(historical, model, definition, v34.STANDARD_COST, 0)
        historical_obs = v47._observe(historical, historical_stream, True)["historical_2018_2020"]
        fold_obs = [
            metrics(streams[0].values[index], streams[0].benchmark[index], streams[0].active[index])
            for index in folds
        ]
        oos = standard["development_oos_2024_2025"]
        consumed = standard["consumed_2026_all"]
        z_score = float(oos["information_ratio"]) * math.sqrt(max(1, int(oos["trades"])) / 252)
        gates = {
            "standard_primary": v13._primary(standard),
            "cost_18bp_primary": v13._primary(cost),
            "delay_5min_primary": v13._primary(delay),
            "four_of_five_positive_folds": sum(float(x["annualized_return"]) > 0 for x in fold_obs)
            >= 4,
            "historical_positive_mdd_below_20pct": float(historical_obs["annualized_return"]) > 0
            and float(historical_obs["max_drawdown"]) < 0.20,
            "parameter_neighborhood_75pct_positive": float(item["neighbor_positive_share"]) >= 0.75,
            "global_bonferroni_5pct": min(
                1.0, 2.0 * v47._normal_tail(abs(z_score)) * max(1, planned)
            )
            < 0.05,
            "consumed_2026_total_above_5pct": float(consumed["total_return"])
            > WEAK_MARKET_2026_MIN_TOTAL_RETURN,
        }
        economic_names = (
            "standard_primary",
            "cost_18bp_primary",
            "delay_5min_primary",
            "four_of_five_positive_folds",
            "historical_positive_mdd_below_20pct",
            "parameter_neighborhood_75pct_positive",
            "consumed_2026_total_above_5pct",
        )
        pre_null_hits += int(all(gates[name] for name in economic_names))
        records.append(
            {
                "candidate_id": v12._identity(definition, "lev-v57r-"),
                "definition": definition,
                "model": {
                    "mean": model.mean.tolist(),
                    "scale": model.scale.tolist(),
                    "direction": model.direction.tolist(),
                    "reliability": model.reliability.tolist(),
                },
                "development_rank": list(item["rank"]),
                "standard": standard,
                "cost_18bp": cost,
                "delay_5min_9bp": delay,
                "historical_2018_2020": historical_obs,
                "folds": fold_obs,
                "neighbor_positive_share": item["neighbor_positive_share"],
                "gates": gates,
            }
        )
    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "selection_contract": (
            "exactly 100 predeclared multi-factor rounds; factor signs and reliability use "
            "2022-2023 only; frontier ranks use development data; historical and consumed 2026 "
            "are attached only after each round freezes its top five"
        ),
        "revised_2026_gate": {
            "metric": "consumed_2026_all.total_return",
            "operator": ">",
            "threshold": 0.05,
        },
        "scan": {
            "planned_rounds": 100,
            "evaluated_rounds": len(rounds),
            "planned_cells": planned,
            "evaluated_cells": sum(int(x.get("evaluated_cells", 0)) for x in rounds),
            "frozen_frontier": len(frontier),
            "elapsed_seconds": time.perf_counter() - started,
        },
        "pre_factory_null_hits": pre_null_hits,
        "rounds": rounds,
        "records": records,
    }
    v12._atomic(args.output, payload)
    print(json.dumps({"scan": payload["scan"], "pre_factory_null_hits": pre_null_hits}))
    if records:
        best = records[0]
        print(
            json.dumps(
                {
                    "candidate_id": best["candidate_id"],
                    "definition": best["definition"],
                    "oos": best["standard"]["development_oos_2024_2025"],
                    "cost_oos": best["cost_18bp"]["development_oos_2024_2025"],
                    "delay_oos": best["delay_5min_9bp"]["development_oos_2024_2025"],
                    "consumed_2026": best["standard"]["consumed_2026_all"],
                    "historical": best["historical_2018_2020"],
                    "gates": best["gates"],
                }
            )
        )


if __name__ == "__main__":
    main()
