"""Preregistered downside overlays; never modifies the active Paper strategy."""

from __future__ import annotations

import argparse
import json
import math
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import evaluate_full_universe_intraday_v1765_v1864_sector_rotation as shared
import numpy as np
import pandas as pd

from us_intraday_lab.fast_intraday_research import metrics

prior = shared.prior
PROPOSAL = (
    Path(__file__).resolve().parents[1]
    / "research/proposals/full_universe_intraday_v1865_v1964/proposal.json"
)
NAMES = shared.SCENARIO_NAMES


def scaled(stream, weight):
    active = stream.active & (weight > 0)
    return prior.v12.ReturnStream(
        stream.values * weight,
        stream.benchmark * weight,
        active,
        np.where(active, stream.component_trades, 0),
    )


def add(left, right):
    return prior.v12.ReturnStream(
        left.values + right.values,
        left.benchmark + right.benchmark,
        left.active | right.active,
        left.component_trades + right.component_trades,
    )


def baseline_parts(cube, development):
    source = (
        Path(__file__).resolve().parents[1]
        / "artifacts/research/v1563_v1662_sources/full-universe-intraday-v60-exact.json"
    )
    component = next(
        r
        for r in json.loads(source.read_text())["records"]
        if r["candidate_id"] == "lev-v60-b528b229cefeace2"
    )
    models = prior.v44._fit(development, (20, 23, 26, 29), 72)
    anchor = shared.anchored._v45_streams(cube, models)
    sleeve = shared.anchored._component_streams(cube, component)
    coefficients = {
        "sector_breadth": 1,
        "risk_asset_agreement": 1,
        "sector_dispersion": -1,
        "spy_volatility": -1,
    }
    matrix = prior._state_matrix(development, "prior_close")
    train = development.masks()["train_2022_2023"]
    means = {n: float(np.nanmean(matrix[n][train])) for n in coefficients}
    scales = {n: max(1e-8, float(np.nanstd(matrix[n][train]))) for n in coefficients}
    score = prior._state_score(
        prior._state_matrix(cube, "prior_close"), coefficients, means, scales
    )
    weight = np.where(np.isfinite(score) & (score >= -0.08095885648451538), 0.16, 0)
    return tuple(
        (scaled(a, 1 - weight), scaled(c, weight)) for a, c in zip(anchor, sleeve, strict=True)
    )


def prior_loss_mask(values, window=5):
    result = np.zeros(len(values), dtype=bool)
    for i in range(window, len(values)):
        result[i] = np.prod(1 + values[i - window : i]) - 1 < 0
    return result


def overlay(parts, allowed, policy, cap, lagged_loss, valid_state=None):
    if policy == "all_cash_bad":
        left = right = np.where(allowed, 1.0, 0.0)
    elif policy == "all_half_bad":
        left = right = np.where(allowed, 1.0, 0.5)
    elif policy == "anchor_cash_bad":
        left, right = np.where(allowed, 1.0, 0.0), np.ones(len(allowed))
    elif policy == "anchor_half_bad":
        left, right = np.where(allowed, 1.0, 0.5), np.ones(len(allowed))
    elif policy == "lagged_loss_brake_bad":
        left = right = np.where(~allowed & lagged_loss, 0.5, 1.0)
    else:
        raise ValueError("UNKNOWN_RISK_POLICY")
    if not 0 < cap <= 1:
        raise ValueError("GROSS_BUDGET_OUT_OF_RANGE")
    if valid_state is not None:
        left = np.where(valid_state, left, 0.0)
        right = np.where(valid_state, right, 0.0)
    return tuple(add(scaled(a, left * cap), scaled(c, right * cap)) for a, c in parts)


def tail_loss(values):
    count = max(1, math.ceil(len(values) * 0.05))
    return max(0.0, -float(np.mean(np.sort(values)[:count])))


def observations(cube, streams, full=False):
    with ThreadPoolExecutor(max_workers=3) as workers:
        return tuple(workers.map(lambda stream: prior.v47._observe(cube, stream, full), streams))


def fit_state(development, historical, coefficients, clock):
    matrix = prior._state_matrix(development, clock)
    train = development.masks()["train_2022_2023"]
    mean = {n: float(np.nanmean(matrix[n][train])) for n in coefficients}
    scale = {n: max(1e-8, float(np.nanstd(matrix[n][train]))) for n in coefficients}
    return (
        prior._state_score(matrix, coefficients, mean, scale),
        prior._state_score(prior._state_matrix(historical, clock), coefficients, mean, scale),
        {"mean": mean, "scale": scale},
    )


def record(
    development, historical, version, cells, chosen, hist_parts, hist_loss, baseline, proposal
):
    streams = chosen["streams"]
    obs = dict(zip(NAMES, observations(development, streams, True), strict=True))
    params = chosen["definition"]
    hist_streams = overlay(
        hist_parts,
        chosen["historical_allowed"],
        params["policy"],
        params["gross_budget_cap"],
        hist_loss,
        chosen["historical_valid"],
    )
    hist_obs = dict(zip(NAMES, observations(historical, hist_streams, True), strict=True))
    folds, starts, risks = {}, {}, {}
    oosmask = development.masks()["development_oos_2024_2025"]
    for index, name in enumerate(NAMES):
        stream = streams[index]
        folds[name] = [
            metrics(stream.values[m], stream.benchmark[m], stream.active[m])
            for m in np.array_split(np.flatnonzero(development.masks()["development_all"]), 5)
        ]
        starts[name] = {}
        for start in ("2022-01-01", "2023-01-01", "2024-01-01"):
            m = development.masks()["development_all"] & (development.dates >= pd.Timestamp(start))
            starts[name][start] = metrics(stream.values[m], stream.benchmark[m], stream.active[m])
        base_metrics = prior.v47._observe(development, baseline[index])["development_oos_2024_2025"]
        base_tail = tail_loss(baseline[index].values[oosmask])
        risk = obs[name]["development_oos_2024_2025"]
        risks[name] = {
            "mdd_reduction": 1 - risk["max_drawdown"] / base_metrics["max_drawdown"],
            "tail_loss_reduction": 1 - tail_loss(stream.values[oosmask]) / base_tail,
            "daily_expected_shortfall_loss": tail_loss(stream.values[oosmask]),
        }
    neighbors = [
        c
        for c in cells
        if abs(c["q_index"] - chosen["q_index"]) + abs(c["cap_index"] - chosen["cap_index"]) <= 1
    ]
    share = sum(c["primary"] for c in neighbors) / len(neighbors)
    main = obs["standard"]["development_oos_2024_2025"]
    z = main["information_ratio"] * math.sqrt(max(1, main["trades"]) / 252)
    bonf = min(1.0, 2 * prior.v47._normal_tail(abs(z)) * proposal["cumulative_comparison_cells"])
    history = hist_obs["standard"]["historical_2018_2020"]
    gates = {
        **{name + "_primary": shared.template._primary(obs[name]) for name in NAMES},
        "four_of_five_positive_folds_all_scenarios": all(
            sum(r["annualized_return"] > 0 for r in group) >= 4 for group in folds.values()
        ),
        "all_scenario_start_dates_positive": all(
            r["annualized_return"] > 0 for group in starts.values() for r in group.values()
        ),
        "historical_positive_mdd_below_20pct": history["annualized_return"] > 0
        and history["max_drawdown"] < 0.2,
        "parameter_neighbor_70pct_primary": share >= 0.7,
        "consumed_2026q1_above_5pct": obs["standard"]["consumed_2026q1"]["total_return"] > 0.05,
        "consumed_2026_all_above_5pct": obs["standard"]["consumed_2026_all"]["total_return"] > 0.05,
        "mdd_reduction_20pct_all_scenarios": all(r["mdd_reduction"] >= 0.2 for r in risks.values()),
        "tail_loss_reduction_15pct_all_scenarios": all(
            r["tail_loss_reduction"] >= 0.15 for r in risks.values()
        ),
        "global_bonferroni_5pct": bonf < 0.05,
    }
    definition = {
        "version": version,
        **params,
        "anchor_candidate_id": "lev-v1254-de6c18bd7658f359",
        "unchanged_entry_bars": [23, 26, 29],
        "unchanged_exit_bars": [65, 72],
    }
    pre = all(v for k, v in gates.items() if k != "global_bonferroni_5pct")
    return {
        "candidate_id": f"risk-v{version}-" + prior._identity(definition),
        "definition": definition,
        "model": chosen["model"],
        "development_rank": list(chosen["rank"]),
        **obs,
        "historical_scenarios": hist_obs,
        "folds": folds,
        "start_dates": starts,
        "risk_improvement": risks,
        "neighbor_primary_share": share,
        "multiple_comparison": {
            "cumulative_cells": proposal["cumulative_comparison_cells"],
            "bonferroni_p": bonf,
        },
        "gates": gates,
        "pre_native_overlay_null_pass": pre,
        "native_null_status": "NEEDS_NATIVE_OVERLAY_NULL" if pre else "NOT_RUN_PRE_NULL_FAILED",
        "inherited_anchor_factory_null_passed": False,
        "admitted": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    proposal = json.loads(PROPOSAL.read_text())
    contract = shared._contract()
    contract["proposal_sha256"] = shared._sha(PROPOSAL)
    contract["code"][Path(__file__).name] = shared._sha(Path(__file__))
    contract_id = prior._identity(contract)
    contract_path = args.output_dir / "contract.json"
    if contract_path.exists() and json.loads(contract_path.read_text()) != contract:
        raise RuntimeError("CHECKPOINT_IDENTITY_CHANGED")
    prior.v12._atomic(contract_path, contract)
    dev = prior.v53.Cube(args.root, "alpaca", 0)
    hist = prior.v53.Cube(args.root, "historical", 0)
    dev_parts = baseline_parts(dev, dev)
    hist_parts = baseline_parts(hist, dev)
    baseline = tuple(add(a, c) for a, c in dev_parts)
    hist_baseline = tuple(add(a, c) for a, c in hist_parts)
    reference, _ = shared._baseline(dev, Path(__file__).resolve().parents[1])
    np.testing.assert_allclose(baseline[0].values, reference.values, rtol=1e-12, atol=1e-12)
    prior.v12._atomic(
        args.output_dir / "baseline.json",
        dict(zip(NAMES, observations(dev, baseline, True), strict=True)),
    )
    loss, hist_loss = prior_loss_mask(baseline[0].values), prior_loss_mask(hist_baseline[0].values)
    all_records, versions = [], []
    for family, coefficients in proposal["families"]:
        for clock in proposal["clocks"]:
            score, hist_score, model = fit_state(dev, hist, coefficients, clock)
            train = dev.masks()["train_2022_2023"] & np.isfinite(score)
            for policy in proposal["policies"]:
                version = 1865 + len(versions)
                version_started = time.perf_counter()
                path = args.output_dir / f"full-universe-intraday-v{version}-exact.json"
                if path.exists():
                    payload = json.loads(path.read_text())
                    if (
                        payload.get("contract_id") != contract_id
                        or payload.get("version") != version
                        or payload.get("status") != "COMPLETE"
                    ):
                        raise RuntimeError("INVALID_VERSION_CHECKPOINT")
                else:
                    cells = []
                    for qi, q in enumerate(proposal["grid"]["state_quantiles"]):
                        threshold = float(np.quantile(score[train], q))
                        allowed = np.isfinite(score) & (score >= threshold)
                        for ci, cap in enumerate(proposal["grid"]["gross_budget_caps"]):
                            streams = overlay(
                                dev_parts, allowed, policy, cap, loss, np.isfinite(score)
                            )
                            obs = observations(dev, streams)
                            definition = {
                                "family": family,
                                "coefficients": coefficients,
                                "clock": clock,
                                "policy": policy,
                                "state_quantile": q,
                                "state_threshold": threshold,
                                "gross_budget_cap": cap,
                            }
                            cells.append(
                                {
                                    "definition": definition,
                                    "streams": streams,
                                    "rank": shared.stress_rank(obs),
                                    "primary": all(shared.template._primary(o) for o in obs),
                                    "model": model,
                                    "historical_allowed": np.isfinite(hist_score)
                                    & (hist_score >= threshold),
                                    "historical_valid": np.isfinite(hist_score),
                                    "q_index": qi,
                                    "cap_index": ci,
                                }
                            )
                    cells.sort(key=lambda c: c["rank"], reverse=True)
                    records = [
                        record(
                            dev, hist, version, cells, c, hist_parts, hist_loss, baseline, proposal
                        )
                        for c in cells[:3]
                    ]
                    payload = {
                        "status": "COMPLETE",
                        "version": version,
                        "contract_id": contract_id,
                        "evaluated_cells": len(cells),
                        "elapsed_seconds": time.perf_counter() - version_started,
                        "records": records,
                    }
                    prior.v12._atomic(path, payload)
                all_records.extend(payload["records"])
                versions.append(
                    {k: payload[k] for k in ("version", "evaluated_cells", "elapsed_seconds")}
                )
                summary = {
                    "status": "COMPLETE" if version == 1964 else "RUNNING",
                    "version_range": [1865, 1964],
                    "contract_id": contract_id,
                    "completed_versions": len(versions),
                    "evaluated_cells": sum(r["evaluated_cells"] for r in versions),
                    "cumulative_comparison_cells": proposal["cumulative_comparison_cells"],
                    "frontier_records": len(all_records),
                    "pre_native_null_survivors": sum(
                        r["pre_native_overlay_null_pass"] for r in all_records
                    ),
                    "admitted": 0,
                    "rejection_counts": dict(
                        Counter(k for r in all_records for k, v in r["gates"].items() if not v)
                    ),
                    "elapsed_seconds": time.perf_counter() - started,
                    "versions": versions,
                }
                prior.v12._atomic(args.output_dir / "summary.json", summary)
                print(
                    json.dumps(
                        {
                            "completed": len(versions),
                            "pre_native_null_survivors": summary["pre_native_null_survivors"],
                        }
                    ),
                    flush=True,
                )


if __name__ == "__main__":
    main()
