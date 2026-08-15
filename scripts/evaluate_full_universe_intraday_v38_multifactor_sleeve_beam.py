"""Development-only sleeve beam for stable multi-factor intraday models."""

from __future__ import annotations

import argparse
import itertools
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path

import analyze_full_universe_intraday_v34_factors as audit
import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v35_rank_ensemble as v35
import evaluate_full_universe_intraday_v37_stable_factor_vote as v37
import numpy as np
import search_full_universe_intraday_v12_robustness as v12
import search_full_universe_intraday_v13_regime_rotation as v13
import search_full_universe_intraday_v15_prior5 as v15

from us_intraday_lab.fast_intraday_research import metrics

SLOTS = {
    "opening": ((5, 8, 11), (18, 23, 29)),
    "morning": ((17, 23, 29), (36, 42, 47)),
    "midday": ((41, 44, 47, 50), (53, 56)),
    "afternoon": ((47, 53, 59), (66, 72, 77)),
    "late": ((65, 68, 71), (74, 77)),
}
ASSET_PROFILES = {
    "leveraged_focus": {
        "opening": (3, 4),
        "morning": (3, 4),
        "midday": (1, 2, 3, 4),
        "afternoon": (3, 4),
        "late": (3, 4),
    },
    "diversified": {
        "opening": (3, 4),
        "morning": (1, 2, 3, 4),
        "midday": tuple(range(5, 16)),
        "afternoon": (1, 2, 3, 4),
        "late": (1, 2, 3, 4),
    },
    "all_rotation": {name: tuple(range(1, 16)) for name in SLOTS},
}
IC_FLOORS = (0.005, 0.01, 0.02)
SELECTION_MODES = ("group_balanced", "top6")
WEIGHTINGS = ("equal", "reliability")
SCORE_THRESHOLDS = (0.0, 0.5, 1.0)


@dataclass(slots=True)
class Sleeve:
    definition: dict
    model: v35.RankModel
    standard: v12.ReturnStream
    cost: v12.ReturnStream
    delay: v12.ReturnStream
    observations: dict
    rank: tuple[float, float, float]


def _observe(cube: v34.Cube, stream: v12.ReturnStream, full: bool = False):
    masks = cube.masks()
    names = (
        tuple(name for name, mask in masks.items() if mask.any())
        if full
        else v15.DEVELOPMENT_NAMES + ("development_oos_2024_2025",)
    )
    return {
        name: metrics(
            stream.values[masks[name]], stream.benchmark[masks[name]], stream.active[masks[name]]
        )
        for name in names
    }


def _diagnostics(cube: v34.Cube, specification: dict):
    masks = cube.masks()
    matrix, label, finite = v34._matrix(cube, specification, v37.ALL_FACTORS)
    output = {}
    for index, factor in enumerate(v37.ALL_FACTORS):
        results = {
            period: audit._factor_result(matrix[:, :, index], label, finite, masks[period])
            for period in audit.PERIODS
        }
        ics = [float(results[period]["ic"]) for period in audit.PERIODS]
        same_sign = all(np.isfinite(ics)) and (min(ics) > 0 or max(ics) < 0)
        output[factor] = {
            **{f"{period}_ic": float(results[period]["ic"]) for period in audit.PERIODS},
            "reliability": min(abs(value) for value in ics) if same_sign else 0.0,
        }
    return matrix, finite, output


def _model(
    cube: v34.Cube,
    specification: dict,
    matrix: np.ndarray,
    finite: np.ndarray,
    diagnostics: dict,
    ic_floor: float,
    selection_mode: str,
    weighting: str,
    threshold: float,
):
    stable = [
        factor
        for factor in v37.ALL_FACTORS
        if float(diagnostics[factor]["reliability"]) >= ic_floor
    ]
    if selection_mode == "group_balanced":
        selected = []
        for group in v34.FACTOR_GROUPS:
            options = [factor for factor in stable if v37.FACTOR_TO_GROUP[factor] == group]
            if options:
                selected.append(max(options, key=lambda factor: diagnostics[factor]["reliability"]))
    else:
        selected = sorted(
            stable, key=lambda factor: diagnostics[factor]["reliability"], reverse=True
        )[:6]
    if len(selected) < 3:
        return None
    indices = np.array([v37.ALL_FACTORS.index(factor) for factor in selected])
    selected_matrix = matrix[:, :, indices]
    train = cube.masks()["train_2022_2023"]
    values = np.where((train[:, None] & finite)[:, :, None], selected_matrix, np.nan)
    mean = np.nanmean(values, axis=(0, 1))
    scale = np.nanstd(values, axis=(0, 1))
    scale[scale < 1e-8] = 1.0
    direction = np.array(
        [np.sign(diagnostics[factor]["train_2022_2023_ic"]) for factor in selected]
    )
    weights = np.array([diagnostics[factor]["reliability"] for factor in selected])
    if weighting == "equal":
        weights = np.ones(len(selected))
    weights /= weights.sum()
    return v35.RankModel(
        specification,
        tuple(selected),
        mean,
        scale,
        direction,
        weights,
        threshold,
        diagnostics,
    )


def _rank(observations: dict, cost: dict, delay: dict):
    return (
        min(float(observations[name]["annualized_return"]) for name in v15.DEVELOPMENT_NAMES),
        min(
            float(cost["development_oos_2024_2025"]["annualized_return"]),
            float(delay["development_oos_2024_2025"]["annualized_return"]),
        ),
        min(
            float(cost["development_oos_2024_2025"]["information_ratio"]),
            float(delay["development_oos_2024_2025"]["information_ratio"]),
        ),
    )


def _portfolio_rank(cube: v34.Cube, sleeves: tuple[Sleeve, ...]):
    standard = _observe(cube, v13._combine([s.standard for s in sleeves]))
    cost = _observe(cube, v13._combine([s.cost for s in sleeves]))
    delay = _observe(cube, v13._combine([s.delay for s in sleeves]))
    return _rank(standard, cost, delay)


def _beam(cube: v34.Cube, shortlisted: dict[str, list[Sleeve]], width: int):
    beam: list[tuple[tuple[float, float, float], tuple[Sleeve, ...]]] = []
    scanned = 0
    for slot in SLOTS:
        prefixes = [item[1] for item in beam] if beam else [()]
        expanded = []
        for prefix in prefixes:
            for option in [None, *shortlisted[slot]]:
                sleeves = prefix if option is None else prefix + (option,)
                if not sleeves:
                    continue
                boundaries = [
                    (
                        int(item.definition["decision"]) + 1,
                        int(item.definition["exit"]),
                    )
                    for item in sleeves
                ]
                if any(left[1] >= right[0] for left, right in itertools.pairwise(boundaries)):
                    continue
                scanned += 1
                expanded.append((_portfolio_rank(cube, sleeves), sleeves))
        expanded.sort(key=lambda item: item[0], reverse=True)
        unique = {}
        for rank, sleeves in expanded:
            identity = v12._identity([item.definition for item in sleeves], "lev-v38p-")
            unique.setdefault(identity, (rank, sleeves))
            if len(unique) >= width:
                break
        beam = list(unique.values())
    return beam, scanned


def _normal_tail(value: float) -> float:
    return 0.5 * math.erfc(value / math.sqrt(2.0))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--per-slot", default=12, type=int)
    parser.add_argument("--beam-width", default=1000, type=int)
    args = parser.parse_args()
    started = time.perf_counter()
    development = v34.Cube(args.root, "alpaca", 0)
    shortlisted: dict[str, list[Sleeve]] = {slot: [] for slot in SLOTS}
    sleeve_trials = 0
    fitted_trials = 0
    for slot, (decisions, exits) in SLOTS.items():
        candidates = []
        for profile_name, profile in ASSET_PROFILES.items():
            for decision, exit_bar in itertools.product(decisions, exits):
                if exit_bar <= decision + 2:
                    continue
                specification = {
                    "name": slot,
                    "decision": decision,
                    "exit": exit_bar,
                    "assets": profile[slot],
                }
                matrix, finite, diagnostics = _diagnostics(development, specification)
                for ic_floor, selection_mode, weighting, threshold in itertools.product(
                    IC_FLOORS, SELECTION_MODES, WEIGHTINGS, SCORE_THRESHOLDS
                ):
                    sleeve_trials += 1
                    model = _model(
                        development,
                        specification,
                        matrix,
                        finite,
                        diagnostics,
                        ic_floor,
                        selection_mode,
                        weighting,
                        threshold,
                    )
                    if model is None:
                        continue
                    fitted_trials += 1
                    standard = v35._sleeve(development, model, v34.STANDARD_COST, 0)
                    cost = v35._sleeve(development, model, v34.STRESS_COST, 0)
                    delay = v35._sleeve(development, model, v34.STANDARD_COST, 1)
                    observations = _observe(development, standard)
                    cost_obs = _observe(development, cost)
                    delay_obs = _observe(development, delay)
                    definition = {
                        "slot": slot,
                        "profile": profile_name,
                        "decision": decision,
                        "exit": exit_bar,
                        "ic_floor": ic_floor,
                        "selection_mode": selection_mode,
                        "weighting": weighting,
                        "score_threshold": threshold,
                        "factors": model.factors,
                    }
                    candidates.append(
                        Sleeve(
                            definition,
                            model,
                            standard,
                            cost,
                            delay,
                            observations,
                            _rank(observations, cost_obs, delay_obs),
                        )
                    )
        candidates.sort(key=lambda item: item.rank, reverse=True)
        diverse = {}
        for item in candidates:
            key = (
                item.definition["decision"],
                item.definition["exit"],
                item.definition["profile"],
                item.definition["factors"],
            )
            diverse.setdefault(key, item)
            if len(diverse) >= args.per_slot:
                break
        shortlisted[slot] = list(diverse.values())
    frontier, portfolio_trials = _beam(development, shortlisted, args.beam_width)

    # Freeze the development-ranked frontier before historical and consumed diagnostics.
    historical = v34.Cube(args.root, "historical", 0)
    masks = development.masks()
    folds = np.array_split(np.flatnonzero(masks["development_all"]), 5)
    total_trials = sleeve_trials + portfolio_trials
    records = []
    eligible = 0
    diagnostic_hits = 0
    for rank, sleeves in frontier:
        standard_stream = v13._combine([item.standard for item in sleeves])
        cost_stream = v13._combine([item.cost for item in sleeves])
        delay_stream = v13._combine([item.delay for item in sleeves])
        standard = _observe(development, standard_stream, True)
        cost = _observe(development, cost_stream, True)
        delay = _observe(development, delay_stream, True)
        historical_stream = v13._combine(
            [v35._sleeve(historical, item.model, v34.STANDARD_COST, 0) for item in sleeves]
        )
        historical_obs = _observe(historical, historical_stream, True)["historical_2018_2020"]
        fold_obs = [
            metrics(
                standard_stream.values[index],
                standard_stream.benchmark[index],
                standard_stream.active[index],
            )
            for index in folds
        ]
        oos = standard["development_oos_2024_2025"]
        consumed = standard["consumed_2026_all"]
        z_score = float(oos["information_ratio"]) * math.sqrt(max(1, int(oos["trades"])) / 252)
        gates = {
            "standard_primary": v13._primary(standard),
            "cost_18bp_primary": v13._primary(cost),
            "delay_5min_primary": v13._primary(delay),
            "four_of_five_positive_folds": sum(
                float(item["annualized_return"]) > 0 for item in fold_obs
            )
            >= 4,
            "historical_positive_mdd_below_20pct": float(historical_obs["annualized_return"]) > 0
            and float(historical_obs["max_drawdown"]) < 0.20,
            "multiple_comparison_bonferroni_5pct": min(
                1.0, 2.0 * _normal_tail(abs(z_score)) * total_trials
            )
            < 0.05,
            "consumed_2026_total_above_20pct": float(consumed["total_return"]) > 0.20,
            "consumed_2026_mdd_below_20pct": float(consumed["max_drawdown"]) < 0.20,
            "consumed_2026_ir_at_least_1": float(consumed["information_ratio"]) >= 1.0,
            "ablation_evaluated": False,
            "start_date_stress_evaluated": False,
            "parameter_neighborhood_evaluated": False,
        }
        if all(
            gates[name]
            for name in (
                "consumed_2026_total_above_20pct",
                "consumed_2026_mdd_below_20pct",
                "consumed_2026_ir_at_least_1",
            )
        ):
            diagnostic_hits += 1
        if all(gates.values()):
            eligible += 1
        records.append(
            {
                "candidate_id": v12._identity([item.definition for item in sleeves], "lev-v38p-"),
                "sleeves": [item.definition for item in sleeves],
                "development_rank": list(rank),
                "standard": standard,
                "cost_18bp": cost,
                "delay_5min_9bp": delay,
                "historical_2018_2020": historical_obs,
                "folds": fold_obs,
                "gates": gates,
            }
        )
    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "selection_contract": "all factor, sleeve, and portfolio ranking uses 2022-2025 only",
        "factor_version": v34.FACTOR_VERSION,
        "scan": {
            "sleeve_trials": sleeve_trials,
            "fitted_trials": fitted_trials,
            "portfolio_trials": portfolio_trials,
            "total_trials": total_trials,
            "frontier_size": len(records),
            "elapsed_seconds": time.perf_counter() - started,
        },
        "shortlist_sizes": {name: len(items) for name, items in shortlisted.items()},
        "diagnostic_hits": diagnostic_hits,
        "eligible": eligible,
        "records": records,
    }
    v12._atomic(args.output, payload)
    print(json.dumps({key: payload[key] for key in ("scan", "diagnostic_hits", "eligible")}))
    if records:
        best = records[0]
        print(
            json.dumps(
                {
                    "candidate_id": best["candidate_id"],
                    "sleeves": best["sleeves"],
                    "development_rank": best["development_rank"],
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
