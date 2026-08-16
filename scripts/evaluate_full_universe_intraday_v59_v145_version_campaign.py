"""Resumable v59-v145 campaign: one distinct multi-factor hypothesis per version."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path

import analyze_full_universe_intraday_v53_cross_asset_factors as v53
import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v42_multifactor_vol_target as v42
import evaluate_full_universe_intraday_v47_score_slope as v47
import evaluate_full_universe_intraday_v57_hundred_round_multifactor as v57
import numpy as np
import search_full_universe_intraday_v12_robustness as v12
import search_full_universe_intraday_v13_regime_rotation as v13

from us_intraday_lab.fast_intraday_research import metrics

ASSETS = np.array((3, 4))
TIMINGS = ((17, 47), (23, 65), (29, 72), (35, 69), (41, 75))
ALPHAS = (10.0, 100.0, 1000.0)
THRESHOLD_QUANTILES = (0.50, 0.70, 0.85)
TARGETS = (0.30, 0.35)
LOOKBACKS = (15, 20)
TOP_PER_VERSION = 5
GLOBAL_PLANNED_CELLS = 87 * 5 * 3 * 3 * 2 * 2

EXTRA_TEMPLATES = {
    "market_micro_mix": (
        "current_return",
        "recent_return",
        "signed_volume_imbalance",
        "vwap_distance",
        "spy_current",
        "sector_breadth",
    ),
    "relative_volume_state": (
        "relative_return",
        "volume_acceleration",
        "current_rank",
        "qqq_current",
        "risk_asset_agreement",
    ),
    "defensive_rotation": (
        "cyclical_minus_defensive",
        "sector_breadth",
        "sector_dispersion",
        "spy_current",
        "prior20_return",
    ),
    "intraday_exhaustion": (
        "current_return",
        "recent_return",
        "path_efficiency",
        "range_ratio",
        "volume_acceleration",
        "leverage_residual",
    ),
    "prior_trend_quality": (
        "prior1_return",
        "prior20_return",
        "prior20_rank",
        "trend_consistency",
        "path_efficiency",
    ),
    "breadth_volatility": (
        "sector_breadth",
        "sector_dispersion",
        "realized_volatility",
        "spy_volatility",
        "risk_asset_agreement",
    ),
    "tech_residual_reclaim": (
        "leverage_residual",
        "tech_minus_market",
        "qqq_minus_iwm",
        "vwap_distance",
        "recent_return",
    ),
    "smallcap_confirmation": (
        "iwm_current",
        "qqq_minus_iwm",
        "cyclical_minus_defensive",
        "current_rank",
        "relative_return",
    ),
    "multi_state": (
        "gap",
        "prior1_return",
        "prior20_return",
        "spy_prior20",
        "spy_current",
        "sector_breadth",
        "sector_dispersion",
    ),
}
TEMPLATES = {**v57.TEMPLATES, **EXTRA_TEMPLATES}
ENGINES = ("ridge_static", "ridge_spy_regime", "ridge_dual_clock")


@dataclass(slots=True)
class RidgeModel:
    factors: tuple[str, ...]
    decision: int
    exit_bar: int
    alpha: float
    mean: np.ndarray
    scale: np.ndarray
    coefficients: np.ndarray
    negative_coefficients: np.ndarray | None
    threshold: float


def _identity(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _versions() -> list[dict]:
    versions = []
    version = 59
    for engine in ENGINES:
        for template, factors in TEMPLATES.items():
            versions.append(
                {
                    "version": version,
                    "engine": engine,
                    "template": template,
                    "factors": factors,
                }
            )
            version += 1
    if version != 146 or len(versions) != 87:
        raise RuntimeError("version campaign must map exactly v59 through v145")
    return versions


def _solve(values: np.ndarray, target: np.ndarray, alpha: float) -> np.ndarray:
    return np.linalg.solve(values.T @ values + alpha * np.eye(values.shape[1]), values.T @ target)


def _fit(
    cube: v53.Cube,
    factors: tuple[str, ...],
    decision: int,
    exit_bar: int,
    alpha: float,
    quantile: float,
    engine: str,
) -> RidgeModel | None:
    specification = {"decision": decision, "exit": exit_bar, "assets": ASSETS}
    matrix, label, finite = v34._matrix(cube, specification, factors)
    train = cube.masks()["train_2022_2023"]
    selected = train[:, None] & finite
    values = matrix[selected]
    target = label[selected]
    if len(target) < 100:
        return None
    mean = values.mean(axis=0)
    scale = values.std(axis=0)
    scale[scale < 1e-8] = 1.0
    standardized = (values - mean) / scale
    negative_coefficients = None
    if engine == "ridge_spy_regime":
        spy = cube.factors(decision)["spy_current"][:, ASSETS][selected]
        positive = spy > 0.0
        if positive.sum() < 50 or (~positive).sum() < 50:
            return None
        coefficients = _solve(standardized[positive], target[positive], alpha)
        negative_coefficients = _solve(standardized[~positive], target[~positive], alpha)
    else:
        coefficients = _solve(standardized, target, alpha)
    prediction = _predict_matrix(
        cube,
        factors,
        decision,
        exit_bar,
        mean,
        scale,
        coefficients,
        negative_coefficients,
    )
    best = np.max(prediction, axis=1)
    threshold_values = best[train & np.isfinite(best)]
    if not len(threshold_values):
        return None
    threshold = float(np.quantile(threshold_values, quantile))
    return RidgeModel(
        factors,
        decision,
        exit_bar,
        alpha,
        mean,
        scale,
        coefficients,
        negative_coefficients,
        threshold,
    )


def _predict_matrix(
    cube: v53.Cube,
    factors: tuple[str, ...],
    decision: int,
    exit_bar: int,
    mean: np.ndarray,
    scale: np.ndarray,
    coefficients: np.ndarray,
    negative_coefficients: np.ndarray | None,
) -> np.ndarray:
    specification = {"decision": decision, "exit": exit_bar, "assets": ASSETS}
    matrix, _, _ = v34._matrix(cube, specification, factors)
    standardized = (matrix - mean) / scale
    prediction = np.einsum("saf,f->sa", standardized, coefficients)
    if negative_coefficients is not None:
        negative = np.einsum("saf,f->sa", standardized, negative_coefficients)
        spy_positive = cube.factors(decision)["spy_current"][:, ASSETS] > 0.0
        prediction = np.where(spy_positive, prediction, negative)
    return np.where(np.isfinite(matrix).all(axis=2), prediction, -np.inf)


def _prediction(cube: v53.Cube, model: RidgeModel) -> np.ndarray:
    return _predict_matrix(
        cube,
        model.factors,
        model.decision,
        model.exit_bar,
        model.mean,
        model.scale,
        model.coefficients,
        model.negative_coefficients,
    )


def _signal(
    cube: v53.Cube,
    model: RidgeModel,
    engine: str,
) -> tuple[np.ndarray, np.ndarray]:
    prediction = _prediction(cube, model)
    local = np.argmax(prediction, axis=1)
    selected = ASSETS[local]
    best = prediction[cube.rows, local]
    active = np.isfinite(best) & (best >= model.threshold)
    if engine == "ridge_dual_clock":
        earlier = RidgeModel(
            model.factors,
            model.decision - 3,
            model.exit_bar,
            model.alpha,
            model.mean,
            model.scale,
            model.coefficients,
            None,
            model.threshold,
        )
        earlier_prediction = _prediction(cube, earlier)
        earlier_local = np.argmax(earlier_prediction, axis=1)
        earlier_selected = ASSETS[earlier_local]
        earlier_best = earlier_prediction[cube.rows, earlier_local]
        active &= (
            (earlier_selected == selected)
            & np.isfinite(earlier_best)
            & (earlier_best >= model.threshold)
        )
    return selected, active


def _raw(
    cube: v53.Cube,
    model: RidgeModel,
    engine: str,
    cost: float,
    delay: int,
) -> v12.ReturnStream:
    selected, active = _signal(cube, model, engine)
    entry = model.decision + 1 + delay
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
    return v12.ReturnStream(values, benchmark, active, active.astype(int))


def _streams(
    cube: v53.Cube,
    model: RidgeModel,
    engine: str,
    target: float,
    lookback: int,
):
    raw = (
        _raw(cube, model, engine, v34.STANDARD_COST, 0),
        _raw(cube, model, engine, v34.STRESS_COST, 0),
        _raw(cube, model, engine, v34.STANDARD_COST, 1),
    )
    exposure = v42._exposure(raw[0].values, lookback, target, 0.0)
    return tuple(v42._scaled(stream, exposure) for stream in raw)


def _definition(specification: dict, model: RidgeModel, target: float, lookback: int) -> dict:
    return {
        **specification,
        "decision": model.decision,
        "exit": model.exit_bar,
        "alpha": model.alpha,
        "threshold_quantile": next(
            quantile
            for quantile in THRESHOLD_QUANTILES
            if math.isclose(model.threshold, model.threshold)
        ),
        "score_threshold": model.threshold,
        "target_volatility": target,
        "lookback": lookback,
    }


def _model_payload(model: RidgeModel) -> dict:
    return {
        "mean": model.mean.tolist(),
        "scale": model.scale.tolist(),
        "coefficients": model.coefficients.tolist(),
        "negative_coefficients": (
            model.negative_coefficients.tolist()
            if model.negative_coefficients is not None
            else None
        ),
        "threshold": model.threshold,
    }


def _neighbor_share(definition: dict, cells: list[dict]) -> float:
    varying = ("decision", "alpha", "threshold_quantile", "target_volatility", "lookback")
    neighbors = [
        item
        for item in cells
        if sum(item["definition"][name] != definition[name] for name in varying) == 1
    ]
    if not neighbors:
        return 0.0
    return sum(
        float(item["observations"][0]["development_oos_2024_2025"]["annualized_return"]) > 0
        for item in neighbors
    ) / len(neighbors)


def _version_path(output_dir: Path, version: int) -> Path:
    return output_dir / f"full-universe-intraday-v{version}-exact.json"


def _run_version(
    development: v53.Cube,
    historical: v53.Cube,
    specification: dict,
    output_dir: Path,
) -> dict:
    version_started = time.perf_counter()
    cells = []
    for (decision, exit_bar), alpha, quantile in itertools.product(
        TIMINGS, ALPHAS, THRESHOLD_QUANTILES
    ):
        model = _fit(
            development,
            tuple(specification["factors"]),
            decision,
            exit_bar,
            alpha,
            quantile,
            str(specification["engine"]),
        )
        if model is None:
            continue
        for target, lookback in itertools.product(TARGETS, LOOKBACKS):
            streams = _streams(
                development,
                model,
                str(specification["engine"]),
                target,
                lookback,
            )
            observations = [v47._observe(development, stream) for stream in streams]
            definition = {
                **specification,
                "decision": decision,
                "exit": exit_bar,
                "alpha": alpha,
                "threshold_quantile": quantile,
                "score_threshold": model.threshold,
                "target_volatility": target,
                "lookback": lookback,
            }
            cells.append(
                {
                    "definition": definition,
                    "model": model,
                    "streams": streams,
                    "observations": observations,
                    "rank": v47._rank(*observations),
                }
            )
    cells.sort(key=lambda item: item["rank"], reverse=True)
    frozen = cells[:TOP_PER_VERSION]
    folds = np.array_split(np.flatnonzero(development.masks()["development_all"]), 5)
    records = []
    pre_null_hits = 0
    for item in frozen:
        definition = item["definition"]
        model = item["model"]
        streams = item["streams"]
        standard, cost, delay = [v47._observe(development, stream, True) for stream in streams]
        historical_stream = _streams(
            historical,
            model,
            str(specification["engine"]),
            float(definition["target_volatility"]),
            int(definition["lookback"]),
        )[0]
        historical_obs = v47._observe(historical, historical_stream, True)["historical_2018_2020"]
        fold_obs = [
            metrics(streams[0].values[index], streams[0].benchmark[index], streams[0].active[index])
            for index in folds
        ]
        neighbor_share = _neighbor_share(definition, cells)
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
            "parameter_neighborhood_75pct_positive": neighbor_share >= 0.75,
            "global_bonferroni_5pct": min(
                1.0,
                2.0 * v47._normal_tail(abs(z_score)) * GLOBAL_PLANNED_CELLS,
            )
            < 0.05,
            "consumed_2026_total_above_5pct": float(consumed["total_return"]) > 0.05,
        }
        core = (
            "standard_primary",
            "cost_18bp_primary",
            "delay_5min_primary",
            "four_of_five_positive_folds",
            "historical_positive_mdd_below_20pct",
            "parameter_neighborhood_75pct_positive",
            "consumed_2026_total_above_5pct",
        )
        pre_null_hits += int(all(gates[name] for name in core))
        records.append(
            {
                "candidate_id": f"lev-v{specification['version']}-" + _identity(definition)[:16],
                "definition": definition,
                "model": _model_payload(model),
                "development_rank": list(item["rank"]),
                "standard": standard,
                "cost_18bp": cost,
                "delay_5min_9bp": delay,
                "historical_2018_2020": historical_obs,
                "folds": fold_obs,
                "neighbor_positive_share": neighbor_share,
                "gates": gates,
            }
        )
    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "version": int(specification["version"]),
        "specification": specification,
        "specification_sha256": _identity(specification),
        "selection_contract": (
            "factor model and engine are version-frozen; coefficients, directions, regime "
            "splits, and score thresholds use 2022-2023 only; top five are frozen before "
            "historical and consumed-2026 diagnostics"
        ),
        "global_multiple_comparison_cells": GLOBAL_PLANNED_CELLS,
        "scan": {
            "planned_cells": 180,
            "evaluated_cells": len(cells),
            "frozen_frontier": len(frozen),
            "elapsed_seconds": time.perf_counter() - version_started,
        },
        "pre_factory_null_hits": pre_null_hits,
        "records": records,
    }
    v12._atomic(_version_path(output_dir, int(specification["version"])), payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    started = time.perf_counter()
    versions = _versions()
    development = v53.Cube(args.root, "alpaca", 0)
    historical = v53.Cube(args.root, "historical", 0)
    summaries = []
    for index, specification in enumerate(versions, start=1):
        path = _version_path(args.output_dir, int(specification["version"]))
        if args.resume and path.is_file():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if existing.get("status") != "COMPLETE" or existing.get(
                "specification_sha256"
            ) != _identity(specification):
                raise ValueError(f"v{specification['version']} checkpoint identity mismatch")
            payload = existing
        else:
            payload = _run_version(development, historical, specification, args.output_dir)
        best = payload["records"][0] if payload["records"] else None
        summaries.append(
            {
                "version": specification["version"],
                "engine": specification["engine"],
                "template": specification["template"],
                "scan": payload["scan"],
                "pre_factory_null_hits": payload["pre_factory_null_hits"],
                "best_candidate_id": best["candidate_id"] if best else None,
                "best_oos_annualized_return": (
                    best["standard"]["development_oos_2024_2025"]["annualized_return"]
                    if best
                    else None
                ),
                "best_consumed_2026_total_return": (
                    best["standard"]["consumed_2026_all"]["total_return"] if best else None
                ),
            }
        )
        v12._atomic(
            args.summary,
            {
                "schema_version": "1.0.0",
                "status": "RUNNING" if index < len(versions) else "COMPLETE",
                "version_range": [59, 145],
                "planned_versions": 87,
                "completed_versions": index,
                "global_multiple_comparison_cells": GLOBAL_PLANNED_CELLS,
                "elapsed_seconds": time.perf_counter() - started,
                "versions": summaries,
            },
        )
        print(
            json.dumps(
                {
                    "progress": f"{index}/87",
                    "version": specification["version"],
                    "pre_factory_null_hits": payload["pre_factory_null_hits"],
                    "best_oos_annualized_return": summaries[-1]["best_oos_annualized_return"],
                    "best_consumed_2026_total_return": summaries[-1][
                        "best_consumed_2026_total_return"
                    ],
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
