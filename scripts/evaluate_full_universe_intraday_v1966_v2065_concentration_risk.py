"""Frozen concentration and multifactor downside overlay campaign."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import time
from pathlib import Path

import evaluate_full_universe_intraday_v1765_v1864_sector_rotation as shared
import evaluate_full_universe_intraday_v1865_v1964_risk_overlay as risk
import numpy as np
import pandas as pd

from us_intraday_lab.fast_intraday_research import metrics

prior = shared.prior
anchored = shared.anchored
PROPOSAL = Path(__file__).resolve().parents[1] / (
    "research/proposals/full_universe_intraday_v1966_v2065_concentration_risk/proposal.json"
)
CODE_PATH = Path(__file__)
SCENARIOS = risk.NAMES
ASSETS = np.array((3, 4))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def anchor_selected(cube, models) -> np.ndarray:
    selected = np.full(len(cube.sessions), -1, dtype=int)
    previous_asset = np.full(len(cube.sessions), -1, dtype=int)
    previous_above = np.zeros(len(cube.sessions), dtype=bool)
    for model in models:
        score = anchored.v45._score(cube, model, 72, "reliability")
        local = np.argmax(score, axis=1)
        best_asset = ASSETS[local]
        best_score = score[cube.rows, local]
        above = np.isfinite(best_score) & (best_score >= 0.75)
        trigger = (selected < 0) & above & previous_above & (previous_asset == best_asset)
        selected[trigger] = best_asset[trigger]
        previous_asset, previous_above = best_asset, above
    return selected


def factor_matrix(cube) -> tuple[np.ndarray, tuple[str, ...]]:
    f = cube.factors(23)
    leveraged = ASSETS
    columns = (
        f["spy_current"][:, 0],
        f["spy_volatility"][:, 0],
        f["sector_breadth"][:, 0],
        f["sector_dispersion"][:, 0],
        f["risk_asset_agreement"][:, 0],
        f["cyclical_minus_defensive"][:, 0],
        f["tech_minus_market"][:, 0],
        np.nanmean(f["current_return"][:, leveraged], axis=1),
        np.nanmin(f["current_return"][:, leveraged], axis=1),
        np.ptp(f["current_return"][:, leveraged], axis=1),
        np.nanmean(f["recent_return"][:, leveraged], axis=1),
        np.nanmin(f["recent_return"][:, leveraged], axis=1),
        np.nanmean(f["path_efficiency"][:, leveraged], axis=1),
        np.nanmax(f["realized_volatility"][:, leveraged], axis=1),
        np.nanmean(f["close_location"][:, leveraged], axis=1),
        np.nanmean(f["signed_volume_imbalance"][:, leveraged], axis=1),
    )
    names = (
        "spy_current",
        "spy_volatility",
        "sector_breadth",
        "sector_dispersion",
        "risk_asset_agreement",
        "cyclical_minus_defensive",
        "tech_minus_market",
        "leveraged_current_mean",
        "leveraged_current_min",
        "leveraged_current_spread",
        "leveraged_recent_mean",
        "leveraged_recent_min",
        "leveraged_path_efficiency_mean",
        "leveraged_realized_volatility_max",
        "leveraged_close_location_mean",
        "leveraged_signed_volume_imbalance_mean",
    )
    return np.column_stack(columns), names


def fit_prediction(cube, target, alpha=10.0):
    matrix, names = factor_matrix(cube)
    train = cube.masks()["train_2022_2023"]
    valid = train & np.isfinite(matrix).all(axis=1) & np.isfinite(target)
    values, labels = matrix[valid], target[valid]
    mean, scale = values.mean(axis=0), values.std(axis=0)
    scale[scale < 1e-8] = 1.0
    standardized = (values - mean) / scale
    label_mean = float(labels.mean())
    coefficients = np.linalg.solve(
        standardized.T @ standardized + alpha * np.eye(standardized.shape[1]),
        standardized.T @ (labels - label_mean),
    )
    prediction = np.full(len(matrix), np.nan)
    finite = np.isfinite(matrix).all(axis=1)
    prediction[finite] = label_mean + ((matrix[finite] - mean) / scale) @ coefficients
    model = {
        "factor_names": names,
        "mean": mean.tolist(),
        "scale": scale.tolist(),
        "coefficients": coefficients.tolist(),
        "intercept": label_mean,
        "alpha": alpha,
    }
    return prediction, model


def predict(cube, model):
    matrix, names = factor_matrix(cube)
    assert tuple(model["factor_names"]) == names
    mean, scale, coefficients = map(
        np.asarray, (model["mean"], model["scale"], model["coefficients"])
    )
    output = np.full(len(matrix), np.nan)
    finite = np.isfinite(matrix).all(axis=1)
    output[finite] = model["intercept"] + ((matrix[finite] - mean) / scale) @ coefficients
    return output


def same_symbol(cube, models, component_record, parts):
    anchor = anchor_selected(cube, models)
    model = anchored._ridge_model(component_record)
    component, _ = anchored.campaign._signal(
        cube, model, str(component_record["definition"]["engine"])
    )
    return (anchor == component) & parts[0][0].active & parts[0][1].active


def apply(parts, multiplier):
    return tuple(risk.scaled(risk.add(a, c), multiplier) for a, c in parts)


def tail(values):
    return risk.tail_loss(values)


def observe(cube, streams):
    return {
        name: prior.v47._observe(cube, stream, True)
        for name, stream in zip(SCENARIOS, streams, strict=True)
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    proposal = json.loads(PROPOSAL.read_text())
    args.output.mkdir(parents=True, exist_ok=True)
    contract = {
        "proposal_sha256": sha(PROPOSAL),
        "code_sha256": sha(CODE_PATH),
        "proposal_version": proposal["proposal_version"],
    }
    prior.v12._atomic(args.output / "contract.json", contract)
    dev, hist = prior.v53.Cube(args.root, "alpaca", 0), prior.v53.Cube(args.root, "historical", 0)
    dev_parts, hist_parts = risk.baseline_parts(dev, dev), risk.baseline_parts(hist, dev)
    baseline, hist_baseline = (
        apply(dev_parts, np.ones(len(dev.sessions))),
        apply(hist_parts, np.ones(len(hist.sessions))),
    )
    base_obs, hist_base_obs = observe(dev, baseline), observe(hist, hist_baseline)
    prediction, model = fit_prediction(dev, baseline[0].values)
    hist_prediction = predict(hist, model)
    train_valid = dev.masks()["train_2022_2023"] & np.isfinite(prediction)
    source = Path(__file__).resolve().parents[1] / (
        "artifacts/research/v1563_v1662_sources/full-universe-intraday-v60-exact.json"
    )
    component_record = next(
        r
        for r in json.loads(source.read_text())["records"]
        if r["candidate_id"] == "lev-v60-b528b229cefeace2"
    )
    models = prior.v44._fit(dev, (20, 23, 26, 29), 72)
    same, hist_same = (
        same_symbol(dev, models, component_record, dev_parts),
        same_symbol(hist, models, component_record, hist_parts),
    )
    grid = list(
        itertools.product(
            proposal["grid"]["same_symbol_gross_caps"],
            proposal["grid"]["risk_score_quantiles"],
            proposal["grid"]["bad_state_multipliers"],
        )
    )
    if len(grid) != 100:
        raise RuntimeError("GRID_NOT_100")
    records, primary_flags = [], {}
    oos = dev.masks()["development_oos_2024_2025"]
    for offset, (concentration_cap, quantile, bad_multiplier) in enumerate(grid):
        threshold = float(np.quantile(prediction[train_valid], quantile))
        multiplier = np.where(same, concentration_cap, 1.0)
        multiplier *= np.where(
            np.isfinite(prediction), np.where(prediction < threshold, bad_multiplier, 1.0), 0.0
        )
        hist_multiplier = np.where(hist_same, concentration_cap, 1.0)
        hist_multiplier *= np.where(
            np.isfinite(hist_prediction),
            np.where(hist_prediction < threshold, bad_multiplier, 1.0),
            0.0,
        )
        streams, hist_streams = apply(dev_parts, multiplier), apply(hist_parts, hist_multiplier)
        observations, historical = observe(dev, streams), observe(hist, hist_streams)
        risks = {}
        gates = {}
        for index, name in enumerate(SCENARIOS):
            candidate = observations[name]["development_oos_2024_2025"]
            base = base_obs[name]["development_oos_2024_2025"]
            risks[name] = {
                "mdd_reduction": 1 - candidate["max_drawdown"] / base["max_drawdown"],
                "tail_loss_reduction": 1
                - tail(streams[index].values[oos]) / tail(baseline[index].values[oos]),
            }
            gates[f"{name}_primary"] = candidate["annualized_return"] >= 0.5 and (
                candidate["max_drawdown"] < 0.2 and candidate["information_ratio"] >= 1.0
            )
        folds = [
            metrics(streams[0].values[x], streams[0].benchmark[x], streams[0].active[x])
            for x in np.array_split(np.flatnonzero(dev.masks()["development_all"]), 5)
        ]
        starts = {}
        for start in ("2022-01-01", "2023-01-01", "2024-01-01"):
            mask = dev.masks()["development_all"] & (dev.dates >= pd.Timestamp(start))
            starts[start] = metrics(
                streams[0].values[mask], streams[0].benchmark[mask], streams[0].active[mask]
            )
        hist_metric = historical["standard"]["historical_2018_2020"]
        gates.update(
            {
                "risk_reduction": all(
                    r["mdd_reduction"] >= 0.2 and r["tail_loss_reduction"] >= 0.15
                    for r in risks.values()
                ),
                "four_of_five_positive_folds": sum(f["annualized_return"] > 0 for f in folds) >= 4,
                "all_start_dates_positive": all(
                    s["annualized_return"] > 0 for s in starts.values()
                ),
                "historical_positive_mdd_below_20pct": hist_metric["annualized_return"] > 0
                and hist_metric["max_drawdown"] < 0.2,
                "consumed_2026q1_above_5pct": observations["standard"]["consumed_2026q1"][
                    "total_return"
                ]
                >= 0.05,
            }
        )
        main_metric = observations["standard"]["development_oos_2024_2025"]
        z = main_metric["information_ratio"] * math.sqrt(max(1, main_metric["trades"]) / 252)
        bonf = min(
            1.0, 2 * prior.v47._normal_tail(abs(z)) * proposal["cumulative_comparison_cells"]
        )
        gates["global_bonferroni"] = bonf < 0.05
        version = proposal["first_version"] + offset
        identity = {
            "version": version,
            "concentration_cap": concentration_cap,
            "risk_quantile": quantile,
            "bad_state_multiplier": bad_multiplier,
            "threshold": threshold,
        }
        key = (concentration_cap, quantile, bad_multiplier)
        primary_flags[key] = all(gates[f"{name}_primary"] for name in SCENARIOS)
        records.append(
            {
                "candidate_id": f"risk-v{version}-" + prior._identity(identity),
                "definition": identity,
                "model": model,
                **observations,
                "historical_scenarios": historical,
                "risk_improvement": risks,
                "folds": folds,
                "start_dates": starts,
                "gates": gates,
                "multiple_comparison": {
                    "bonferroni_p": bonf,
                    "cumulative_cells": proposal["cumulative_comparison_cells"],
                },
                "same_symbol_days": int(same.sum()),
                "admitted": False,
            }
        )
    for record in records:
        d = record["definition"]
        neighbors = [
            flag
            for (c, q, b), flag in primary_flags.items()
            if abs(
                proposal["grid"]["same_symbol_gross_caps"].index(c)
                - proposal["grid"]["same_symbol_gross_caps"].index(d["concentration_cap"])
            )
            + abs(
                proposal["grid"]["risk_score_quantiles"].index(q)
                - proposal["grid"]["risk_score_quantiles"].index(d["risk_quantile"])
            )
            + abs(
                proposal["grid"]["bad_state_multipliers"].index(b)
                - proposal["grid"]["bad_state_multipliers"].index(d["bad_state_multiplier"])
            )
            <= 1
        ]
        share = sum(neighbors) / len(neighbors)
        record["parameter_neighbor_primary_share"] = share
        record["gates"]["parameter_neighbor_70pct_primary"] = share >= 0.7
        pre_null = all(v for k, v in record["gates"].items() if k != "global_bonferroni")
        record["pre_native_overlay_null_pass"] = pre_null
        record["native_null_status"] = "NEEDS_NATIVE_OVERLAY_NULL" if pre_null else "NOT_RUN"
    ranking = sorted(
        records,
        key=lambda r: (
            all(r["gates"][f"{n}_primary"] for n in SCENARIOS),
            min(r["risk_improvement"][n]["mdd_reduction"] for n in SCENARIOS),
            r["standard"]["development_oos_2024_2025"]["annualized_return"],
        ),
        reverse=True,
    )
    result = {
        "status": "COMPLETE",
        "versions": [proposal["first_version"], proposal["last_version"]],
        "hypotheses": 100,
        "elapsed_seconds": time.perf_counter() - started,
        "contract": contract,
        "baseline": base_obs,
        "historical_baseline": hist_base_obs,
        "records": records,
        "ranked_candidate_ids": [r["candidate_id"] for r in ranking],
        "pre_native_overlay_null_passes": sum(r["pre_native_overlay_null_pass"] for r in records),
        "admissions": 0,
    }
    prior.v12._atomic(args.output / "result.json", result)
    print(
        json.dumps(
            {
                "status": "COMPLETE",
                "hypotheses": 100,
                "pre_null_passes": result["pre_native_overlay_null_passes"],
                "best": ranking[0]["candidate_id"],
                "elapsed_seconds": round(result["elapsed_seconds"], 3),
            }
        )
    )


if __name__ == "__main__":
    main()
