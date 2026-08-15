"""Development-frozen multi-factor minute-path research campaign."""

from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import search_full_universe_intraday_v12_robustness as v12
import search_full_universe_intraday_v13_regime_rotation as v13
import search_full_universe_intraday_v15_prior5 as v15
import search_full_universe_intraday_v21_vwap_structure as v21

from us_intraday_lab.fast_intraday_research import metrics

STANDARD_COST = 0.0009
STRESS_COST = 0.0018
FACTOR_VERSION = "multifactor-minute-path-1.0.0"
FACTOR_GROUPS = {
    "trend": ("current_return", "recent_return", "relative_return", "path_efficiency"),
    "flow": ("trend_consistency", "signed_volume_imbalance", "volume_acceleration"),
    "structure": ("vwap_distance", "close_location", "range_ratio"),
    "volatility": ("realized_volatility", "session_range"),
    "cross_section": ("current_rank", "prior20_rank", "sector_breadth"),
    "state": ("prior1_return", "prior20_return", "gap", "spy_prior20", "spy_volatility"),
}
FACTOR_SETS = {
    "trend_flow_state": FACTOR_GROUPS["trend"] + FACTOR_GROUPS["flow"] + FACTOR_GROUPS["state"],
    "trend_structure_flow": FACTOR_GROUPS["trend"]
    + FACTOR_GROUPS["structure"]
    + FACTOR_GROUPS["flow"],
    "cross_persistence": FACTOR_GROUPS["trend"]
    + FACTOR_GROUPS["cross_section"]
    + FACTOR_GROUPS["state"],
    "reclaim_quality": (
        "current_return",
        "recent_return",
        "vwap_distance",
        "close_location",
        "signed_volume_imbalance",
        "volume_acceleration",
        "prior1_return",
        "spy_prior20",
    ),
    "volatility_breakout": (
        "current_return",
        "relative_return",
        "path_efficiency",
        "realized_volatility",
        "session_range",
        "range_ratio",
        "signed_volume_imbalance",
        "sector_breadth",
    ),
    "balanced": (
        "current_return",
        "recent_return",
        "relative_return",
        "path_efficiency",
        "signed_volume_imbalance",
        "vwap_distance",
        "close_location",
        "realized_volatility",
        "current_rank",
        "prior20_rank",
        "prior20_return",
        "spy_prior20",
    ),
}
PROFILES = {
    "leveraged_focus": ((3, 4), (3, 4), (1, 2, 3, 4), (3, 4)),
    "diversified": ((3, 4), (1, 2, 3, 4), tuple(range(5, 16)), (1, 2, 3, 4)),
    "all_rotation": ((1, 2, 3, 4), tuple(range(1, 16)), tuple(range(1, 16)), tuple(range(1, 16))),
}
SCHEDULE = (
    {"name": "opening", "decision": 8, "exit": 23},
    {"name": "morning", "decision": 29, "exit": 42},
    {"name": "midday", "decision": 44, "exit": 56},
    {"name": "afternoon", "decision": 59, "exit": 77},
)
ALPHAS = (10.0, 100.0, 1000.0)
QUANTILES = (0.70, 0.85)


@dataclass(slots=True)
class Model:
    specification: dict[str, Any]
    factors: tuple[str, ...]
    mean: np.ndarray
    scale: np.ndarray
    coefficients: np.ndarray
    threshold: float


def _percentile_rank(values: np.ndarray) -> np.ndarray:
    output = np.full_like(values, np.nan)
    for row in range(len(values)):
        finite = np.flatnonzero(np.isfinite(values[row]))
        if len(finite) < 2:
            continue
        order = finite[np.argsort(values[row, finite], kind="stable")]
        output[row, order] = np.arange(len(order)) / (len(order) - 1)
    return output


class Cube(v21.Cube):
    """Exact cube with causal multi-factor minute-path features."""

    def __init__(self, root: Path, source: str, boundary_tolerance: int) -> None:
        super().__init__(root, source, boundary_tolerance)
        exact = (self.first[:, 0, :] <= boundary_tolerance) & (
            self.last[:, 77, :] >= 389 - boundary_tolerance
        )
        daily = np.where(exact, self.closes[:, 77, :] / self.opens[:, 0, :] - 1.0, np.nan)
        self.prior1 = np.full_like(daily, np.nan)
        self.prior20 = np.full_like(daily, np.nan)
        prior_close = np.full_like(daily, np.nan)
        self.prior1[1:] = daily[:-1]
        prior_close[1:] = np.where(exact[:-1], self.closes[:-1, 77, :], np.nan)
        self.gap = self.opens[:, 0, :] / prior_close - 1.0
        for index in range(20, len(self.sessions)):
            window = daily[index - 20 : index]
            valid = np.isfinite(window).all(axis=0)
            self.prior20[index, valid] = np.prod(1.0 + window[:, valid], axis=0) - 1.0
        self.bar_return = self.closes / self.opens - 1.0
        zero = np.zeros((len(self.sessions), 1, len(v12.SYMBOLS)))
        self.bar_volume = np.diff(self.cumulative_volume, axis=1, prepend=zero)
        self._factor_cache: dict[int, dict[str, np.ndarray]] = {}

    def factors(self, decision: int) -> dict[str, np.ndarray]:
        if decision in self._factor_cache:
            return self._factor_cache[decision]
        base = self._features(decision)
        micro = self._micro(decision)
        returns = self.bar_return[:, : decision + 1, :]
        volume = self.bar_volume[:, : decision + 1, :]
        finite = np.isfinite(returns)
        count = finite.sum(axis=1)
        path = np.where(finite, np.abs(returns), 0.0).sum(axis=1)
        path_efficiency = np.divide(
            base["current"], path, out=np.full_like(path, np.nan), where=path > 1e-8
        )
        trend_consistency = np.divide(
            ((returns > 0) & finite).sum(axis=1),
            count,
            out=np.full_like(path, np.nan),
            where=count >= max(2, decision // 2),
        )
        total_volume = np.where(np.isfinite(volume), volume, 0.0).sum(axis=1)
        signed_volume = np.where(finite, np.sign(returns) * volume, 0.0).sum(axis=1)
        signed_volume_imbalance = np.divide(
            signed_volume,
            total_volume,
            out=np.full_like(path, np.nan),
            where=total_volume > 0,
        )
        realized_volatility = np.sqrt(np.where(finite, returns**2, 0.0).sum(axis=1))
        split = max(1, decision - 2)
        recent_volume = np.nanmean(volume[:, split : decision + 1, :], axis=1)
        earlier_volume = np.nanmean(volume[:, :split, :], axis=1)
        volume_acceleration = (
            np.divide(
                recent_volume,
                earlier_volume,
                out=np.full_like(path, np.nan),
                where=earlier_volume > 0,
            )
            - 1.0
        )
        current_rank = _percentile_rank(base["current"][:, 1:])
        prior20_rank = _percentile_rank(self.prior20[:, 1:])
        ranked_current = np.full_like(base["current"], np.nan)
        ranked_prior20 = np.full_like(base["current"], np.nan)
        ranked_current[:, 1:] = current_rank
        ranked_prior20[:, 1:] = prior20_rank
        sector = base["current"][:, v12.SECTORS]
        sector_finite = np.isfinite(sector)
        sector_count = sector_finite.sum(axis=1)
        breadth = np.divide(
            ((sector > 0) & sector_finite).sum(axis=1),
            sector_count,
            out=np.full(len(self.sessions), np.nan),
            where=sector_count >= 7,
        )
        output = {
            "current_return": base["current"],
            "recent_return": base["recent"],
            "relative_return": base["current"] - base["spy"][:, None],
            "path_efficiency": path_efficiency,
            "trend_consistency": trend_consistency,
            "signed_volume_imbalance": signed_volume_imbalance,
            "volume_acceleration": volume_acceleration,
            "vwap_distance": micro["price_vwap"],
            "close_location": micro["close_location"],
            "range_ratio": micro["range_ratio"],
            "realized_volatility": realized_volatility,
            "session_range": micro["session_range"],
            "current_rank": ranked_current,
            "prior20_rank": ranked_prior20,
            "sector_breadth": np.repeat(breadth[:, None], len(v12.SYMBOLS), axis=1),
            "prior1_return": self.prior1,
            "prior20_return": self.prior20,
            "gap": self.gap,
            "spy_prior20": np.repeat(self.prior20[:, 0, None], len(v12.SYMBOLS), axis=1),
            "spy_volatility": np.repeat(realized_volatility[:, 0, None], len(v12.SYMBOLS), axis=1),
        }
        self._factor_cache[decision] = output
        return output


def _matrix(cube: Cube, specification: dict[str, Any], factors: tuple[str, ...]):
    decision = int(specification["decision"])
    exit_bar = int(specification["exit"])
    entry = decision + 1
    assets = np.asarray(specification["assets"], dtype=int)
    available = cube.factors(decision)
    matrix = np.stack([available[name][:, assets] for name in factors], axis=2)
    tolerance = cube.boundary_tolerance
    quality = (cube.first[:, entry, assets] <= entry * 5 + tolerance) & (
        cube.first[:, exit_bar, assets] <= exit_bar * 5 + tolerance
    )
    label = cube.opens[:, exit_bar, assets] / cube.opens[:, entry, assets] - 1.0 - STANDARD_COST
    finite = np.isfinite(matrix).all(axis=2) & quality & np.isfinite(label)
    return matrix, label, finite


def _fit_models(
    cube: Cube,
    factors: tuple[str, ...],
    profile: tuple[tuple[int, ...], ...],
    alpha: float,
    quantile: float,
) -> list[Model]:
    masks = cube.masks()
    train = masks["train_2022_2023"]
    validation = masks["2024"]
    models = []
    for slot, assets in zip(SCHEDULE, profile, strict=True):
        specification = {**slot, "assets": assets}
        matrix, label, finite = _matrix(cube, specification, factors)
        selected = train[:, None] & finite
        values = matrix[selected]
        target = label[selected]
        mean = values.mean(axis=0)
        scale = values.std(axis=0)
        scale[scale < 1e-8] = 1.0
        standardized = (values - mean) / scale
        coefficients = np.linalg.solve(
            standardized.T @ standardized + alpha * np.eye(len(factors)),
            standardized.T @ target,
        )
        prediction = np.einsum("saf,f->sa", (matrix - mean) / scale, coefficients)
        signal_finite = np.isfinite(matrix).all(axis=2)
        prediction = np.where(signal_finite, prediction, -np.inf)
        best = np.max(prediction, axis=1)
        threshold = float(np.quantile(best[validation & np.isfinite(best)], quantile))
        models.append(Model(specification, factors, mean, scale, coefficients, threshold))
    return models


def _sleeve(cube: Cube, model: Model, cost: float, delay: int) -> v12.ReturnStream:
    matrix, _, _ = _matrix(cube, model.specification, model.factors)
    prediction = np.einsum("saf,f->sa", (matrix - model.mean) / model.scale, model.coefficients)
    prediction = np.where(np.isfinite(matrix).all(axis=2), prediction, -np.inf)
    local = np.argmax(prediction, axis=1)
    assets = np.asarray(model.specification["assets"], dtype=int)
    selected = assets[local]
    score = prediction[cube.rows, local]
    entry = int(model.specification["decision"]) + 1 + delay
    exit_bar = int(model.specification["exit"])
    active = np.isfinite(score) & (score >= model.threshold)
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


def _stream(cube: Cube, models: list[Model], cost: float, delay: int):
    return v13._combine([_sleeve(cube, model, cost, delay) for model in models])


def _normal_tail(value: float) -> float:
    return 0.5 * math.erfc(value / math.sqrt(2.0))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    development = Cube(args.root, "alpaca", 0)
    records = []
    model_sets: dict[str, list[Model]] = {}
    standard_streams: dict[str, v12.ReturnStream] = {}
    for factor_set_name, factors in FACTOR_SETS.items():
        for profile_name, profile in PROFILES.items():
            for alpha in ALPHAS:
                for quantile in QUANTILES:
                    definition = {
                        "factor_version": FACTOR_VERSION,
                        "factor_set": factor_set_name,
                        "profile": profile_name,
                        "alpha": alpha,
                        "quantile": quantile,
                        "schedule": SCHEDULE,
                    }
                    candidate_id = v12._identity(definition, "lev-v34m-")
                    models = _fit_models(development, factors, profile, alpha, quantile)
                    model_sets[candidate_id] = models
                    scenario_streams = {
                        "standard": _stream(development, models, STANDARD_COST, 0),
                        "cost_18bp": _stream(development, models, STRESS_COST, 0),
                        "delay_5min_9bp": _stream(development, models, STANDARD_COST, 1),
                    }
                    standard_streams[candidate_id] = scenario_streams["standard"]
                    observations = {
                        name: v13._observe(development, stream)
                        for name, stream in scenario_streams.items()
                    }
                    records.append(
                        {
                            "candidate_id": candidate_id,
                            "definition": definition,
                            "factors": factors,
                            "factor_count": len(factors),
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

    # Frontier is frozen above before either diagnostic source is attached.
    historical = Cube(args.root, "historical", 0)
    folds = np.array_split(np.flatnonzero(development.masks()["development_all"]), 5)
    total_trials = len(records)
    diagnostic_hits = 0
    eligible = 0
    for item in records:
        models = model_sets[item["candidate_id"]]
        historical_obs = v13._observe(historical, _stream(historical, models, STANDARD_COST, 0))
        standard_stream = standard_streams[item["candidate_id"]]
        fold_obs = [
            metrics(
                standard_stream.values[index],
                standard_stream.benchmark[index],
                standard_stream.active[index],
            )
            for index in folds
        ]
        oos = item["standard"]["development_oos_2024_2025"]
        consumed = item["standard"]["consumed_2026_all"]
        hist = historical_obs["historical_2018_2020"]
        z_score = float(oos["information_ratio"]) * math.sqrt(max(1, int(oos["trades"])) / 252)
        bonferroni = min(1.0, 2.0 * _normal_tail(abs(z_score)) * total_trials)
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
            "total_trials": total_trials,
            "bonferroni_p": bonferroni,
        }
        item["gates"] = gates
        item["eligible_for_future_simulation_observation"] = all(gates.values())
        diagnostic_hits += int(gates["consumed_2026_total_above_20pct"])
        eligible += int(item["eligible_for_future_simulation_observation"])
    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "factor_manifest": {
            "version": FACTOR_VERSION,
            "groups": FACTOR_GROUPS,
            "sets": FACTOR_SETS,
            "new_research_factors": (
                "path_efficiency",
                "trend_consistency",
                "signed_volume_imbalance",
                "volume_acceleration",
                "current_rank",
                "prior20_rank",
            ),
            "production_catalog_mutated": False,
        },
        "selection_contract": "joint factor models fit 2022-2023; 2024 thresholds; rank through 2025; consumed 2026 post-freeze",
        "execution_contract": "long-only; gross<=1; no overnight; four non-overlapping sleeves",
        "scan": {
            "factor_sets": len(FACTOR_SETS),
            "profiles": len(PROFILES),
            "alphas": len(ALPHAS),
            "quantiles": len(QUANTILES),
            "total_trials": total_trials,
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
    best = max(
        records, key=lambda item: float(item["standard"]["consumed_2026_all"]["total_return"])
    )
    print(
        json.dumps(
            {
                "candidate_id": best["candidate_id"],
                "definition": best["definition"],
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
