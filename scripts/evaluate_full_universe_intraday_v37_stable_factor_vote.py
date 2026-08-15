"""Cross-period stable multi-factor group-vote strategy campaign."""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import analyze_full_universe_intraday_v34_factors as audit
import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v35_rank_ensemble as v35
import numpy as np
import search_full_universe_intraday_v12_robustness as v12
import search_full_universe_intraday_v13_regime_rotation as v13
import search_full_universe_intraday_v15_prior5 as v15

from us_intraday_lab.fast_intraday_research import metrics

ALL_FACTORS = tuple(
    dict.fromkeys(factor for group in v34.FACTOR_GROUPS.values() for factor in group)
)
FACTOR_TO_GROUP = {
    factor: group for group, factors in v34.FACTOR_GROUPS.items() for factor in factors
}
IC_FLOORS = (0.005, 0.01, 0.02)
SELECTION_MODES = ("group_balanced", "top6")
WEIGHTINGS = ("equal", "reliability")
SCORE_THRESHOLDS = (0.0, 0.5, 1.0)


def _fit_models(
    cube: v34.Cube,
    profile: tuple[tuple[int, ...], ...],
    ic_floor: float,
    selection_mode: str,
    weighting: str,
    score_threshold: float,
) -> list[v35.RankModel] | None:
    masks = cube.masks()
    train = masks["train_2022_2023"]
    models = []
    for slot, assets in zip(v34.SCHEDULE, profile, strict=True):
        specification = {**slot, "assets": assets}
        matrix, label, finite = v34._matrix(cube, specification, ALL_FACTORS)
        diagnostics: dict[str, dict[str, float]] = {}
        stable = []
        for index, factor in enumerate(ALL_FACTORS):
            observations = {
                period: audit._factor_result(matrix[:, :, index], label, finite, masks[period])
                for period in audit.PERIODS
            }
            ics = [float(observations[period]["ic"]) for period in audit.PERIODS]
            same_sign = all(np.isfinite(ics)) and (min(ics) > 0 or max(ics) < 0)
            reliability = min(abs(value) for value in ics) if same_sign else 0.0
            diagnostics[factor] = {
                **{f"{period}_ic": float(observations[period]["ic"]) for period in audit.PERIODS},
                "reliability": reliability,
            }
            if same_sign and reliability >= ic_floor:
                stable.append(factor)
        if selection_mode == "group_balanced":
            selected = []
            for group in v34.FACTOR_GROUPS:
                options = [factor for factor in stable if FACTOR_TO_GROUP[factor] == group]
                if options:
                    selected.append(
                        max(options, key=lambda factor: diagnostics[factor]["reliability"])
                    )
        else:
            selected = sorted(
                stable, key=lambda factor: diagnostics[factor]["reliability"], reverse=True
            )[:6]
        if len(selected) < 3:
            return None
        indices = np.array([ALL_FACTORS.index(factor) for factor in selected])
        selected_matrix = matrix[:, :, indices]
        train_selected = (train[:, None] & finite)[:, :, None]
        values = np.where(train_selected, selected_matrix, np.nan)
        mean = np.nanmean(values, axis=(0, 1))
        scale = np.nanstd(values, axis=(0, 1))
        scale[scale < 1e-8] = 1.0
        direction = np.array(
            [np.sign(diagnostics[factor]["train_2022_2023_ic"]) for factor in selected]
        )
        if weighting == "reliability":
            weights = np.array([diagnostics[factor]["reliability"] for factor in selected])
            weights /= weights.sum()
        else:
            weights = np.full(len(selected), 1.0 / len(selected))
        models.append(
            v35.RankModel(
                specification,
                tuple(selected),
                mean,
                scale,
                direction,
                weights,
                score_threshold,
                diagnostics,
            )
        )
    return models


def _observe_development(cube: v34.Cube, stream: v12.ReturnStream):
    masks = cube.masks()
    names = v15.DEVELOPMENT_NAMES + ("development_oos_2024_2025",)
    return {
        name: metrics(
            stream.values[masks[name]],
            stream.benchmark[masks[name]],
            stream.active[masks[name]],
        )
        for name in names
    }


def _normal_tail(value: float) -> float:
    return 0.5 * math.erfc(value / math.sqrt(2.0))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    development = v34.Cube(args.root, "alpaca", 0)
    planned_trials = (
        len(v34.PROFILES)
        * len(IC_FLOORS)
        * len(SELECTION_MODES)
        * len(WEIGHTINGS)
        * len(SCORE_THRESHOLDS)
    )
    records = []
    model_sets: dict[str, list[v35.RankModel]] = {}
    streams: dict[str, tuple[v12.ReturnStream, v12.ReturnStream, v12.ReturnStream]] = {}
    rejected = 0
    for profile_name, profile in v34.PROFILES.items():
        for ic_floor in IC_FLOORS:
            for selection_mode in SELECTION_MODES:
                for weighting in WEIGHTINGS:
                    for threshold in SCORE_THRESHOLDS:
                        models = _fit_models(
                            development,
                            profile,
                            ic_floor,
                            selection_mode,
                            weighting,
                            threshold,
                        )
                        if models is None:
                            rejected += 1
                            continue
                        definition = {
                            "factor_version": v34.FACTOR_VERSION,
                            "profile": profile_name,
                            "ic_floor": ic_floor,
                            "selection_mode": selection_mode,
                            "weighting": weighting,
                            "score_threshold": threshold,
                        }
                        candidate_id = v12._identity(definition, "lev-v37v-")
                        model_sets[candidate_id] = models
                        standard = v35._stream(development, models, v34.STANDARD_COST, 0)
                        cost = v35._stream(development, models, v34.STRESS_COST, 0)
                        delay = v35._stream(development, models, v34.STANDARD_COST, 1)
                        streams[candidate_id] = (standard, cost, delay)
                        observations = {
                            "standard": _observe_development(development, standard),
                            "cost_18bp": _observe_development(development, cost),
                            "delay_5min_9bp": _observe_development(development, delay),
                        }
                        records.append(
                            {
                                "candidate_id": candidate_id,
                                "definition": definition,
                                "selected_factors_by_sleeve": {
                                    model.specification["name"]: model.factors for model in models
                                },
                                "factor_diagnostics_by_sleeve": {
                                    model.specification["name"]: model.diagnostics
                                    for model in models
                                },
                                "development_rank": [
                                    min(
                                        float(observations["standard"][name]["annualized_return"])
                                        for name in v15.DEVELOPMENT_NAMES
                                    ),
                                    float(
                                        observations["cost_18bp"]["development_oos_2024_2025"][
                                            "annualized_return"
                                        ]
                                    ),
                                    float(
                                        observations["cost_18bp"]["development_oos_2024_2025"][
                                            "information_ratio"
                                        ]
                                    ),
                                ],
                                **observations,
                            }
                        )
    records.sort(key=lambda item: tuple(item["development_rank"]), reverse=True)

    historical = v34.Cube(args.root, "historical", 0)
    folds = np.array_split(np.flatnonzero(development.masks()["development_all"]), 5)
    diagnostic_hits = 0
    eligible = 0
    for item in records:
        models = model_sets[item["candidate_id"]]
        standard, cost, delay = streams[item["candidate_id"]]
        item["standard"] = v13._observe(development, standard)
        item["cost_18bp"] = v13._observe(development, cost)
        item["delay_5min_9bp"] = v13._observe(development, delay)
        historical_obs = v13._observe(
            historical, v35._stream(historical, models, v34.STANDARD_COST, 0)
        )
        fold_obs = [
            metrics(standard.values[index], standard.benchmark[index], standard.active[index])
            for index in folds
        ]
        oos = item["standard"]["development_oos_2024_2025"]
        consumed = item["standard"]["consumed_2026_all"]
        hist = historical_obs["historical_2018_2020"]
        z_score = float(oos["information_ratio"]) * math.sqrt(max(1, int(oos["trades"])) / 252)
        bonferroni = min(1.0, 2.0 * _normal_tail(abs(z_score)) * planned_trials)
        gates = {
            "standard_primary": v15._primary(item["standard"]),
            "cost_18bp_primary": v15._primary(item["cost_18bp"]),
            "delay_5min_primary": v15._primary(item["delay_5min_9bp"]),
            "four_of_five_positive_folds": sum(
                float(fold["annualized_return"]) > 0 for fold in fold_obs
            )
            >= 4,
            "historical_positive_mdd_below_20pct": float(hist["annualized_return"]) > 0
            and float(hist["max_drawdown"]) < 0.20,
            "consumed_2026_total_above_20pct": float(consumed["total_return"]) > 0.20,
            "consumed_2026_mdd_below_20pct": float(consumed["max_drawdown"]) < 0.20,
            "consumed_2026_ir_at_least_1": float(consumed["information_ratio"]) >= 1.0,
            "multiple_comparison_bonferroni_5pct": bonferroni < 0.05,
            "ablation_evaluated": False,
            "start_date_stress_evaluated": False,
            "parameter_neighborhood_evaluated": False,
        }
        item["historical_cross_source"] = historical_obs
        item["development_folds"] = fold_obs
        item["multiple_comparison"] = {
            "planned_trials": planned_trials,
            "bonferroni_p": bonferroni,
        }
        item["gates"] = gates
        item["eligible_for_future_simulation_observation"] = all(gates.values())
        diagnostic_hits += int(gates["consumed_2026_total_above_20pct"])
        eligible += int(item["eligible_for_future_simulation_observation"])
    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "selection_contract": "factor direction must agree in 2022-2023, 2024, and 2025; 2026 post-freeze",
        "factor_model": {
            "factor_version": v34.FACTOR_VERSION,
            "ic_floors": IC_FLOORS,
            "selection_modes": SELECTION_MODES,
            "weightings": WEIGHTINGS,
            "score_thresholds": SCORE_THRESHOLDS,
            "minimum_factors_per_sleeve": 3,
            "production_catalog_mutated": False,
        },
        "execution_contract": "long-only; gross<=1; no overnight; four non-overlapping sleeves",
        "scan": {
            "planned_trials": planned_trials,
            "evaluated_trials": len(records),
            "rejected_insufficient_factors": rejected,
            "frontier_size": len(records),
            "elapsed_seconds": time.perf_counter() - started,
        },
        "diagnostic_2026_above_20_count": diagnostic_hits,
        "eligible_count": eligible,
        "frontier": records,
    }
    v12._atomic(args.output, payload)
    print(
        json.dumps(
            {"scan": payload["scan"], "diagnostic_hits": diagnostic_hits, "eligible": eligible}
        )
    )
    if records:
        best = max(
            records,
            key=lambda item: float(item["standard"]["consumed_2026_all"]["total_return"]),
        )
        print(
            json.dumps(
                {
                    "candidate_id": best["candidate_id"],
                    "definition": best["definition"],
                    "selected_factors_by_sleeve": best["selected_factors_by_sleeve"],
                    "development_rank": best["development_rank"],
                    "oos": best["standard"]["development_oos_2024_2025"],
                    "cost_oos": best["cost_18bp"]["development_oos_2024_2025"],
                    "delay_oos": best["delay_5min_9bp"]["development_oos_2024_2025"],
                    "historical": best["historical_cross_source"]["historical_2018_2020"],
                    "consumed_2026": best["standard"]["consumed_2026_all"],
                    "gates": best["gates"],
                },
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
