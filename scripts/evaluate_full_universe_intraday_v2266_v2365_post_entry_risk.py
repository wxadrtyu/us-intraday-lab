"""Causal close-confirmed, next-open post-entry risk campaign for frozen v1254."""

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
    "research/proposals/full_universe_intraday_v2266_v2365_post_entry_risk/proposal.json"
)
SCENARIOS = risk.NAMES
ASSETS = np.array((3, 4))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def component_record() -> dict:
    source = Path(__file__).resolve().parents[1] / (
        "artifacts/research/v1563_v1662_sources/full-universe-intraday-v60-exact.json"
    )
    return next(
        item
        for item in json.loads(source.read_text())["records"]
        if item["candidate_id"] == "lev-v60-b528b229cefeace2"
    )


def anchor_route(cube, models, delay: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    selected = np.full(len(cube.sessions), -1, dtype=int)
    entry = np.full(len(cube.sessions), -1, dtype=int)
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
        entry[trigger] = model.decision + 1 + delay
        previous_asset, previous_above = best_asset, above
    safe_asset, safe_entry = np.maximum(selected, 0), np.maximum(entry, 0)
    active = (selected >= 0) & (safe_entry < 72)
    active &= cube.first[cube.rows, safe_entry, safe_asset] <= (
        safe_entry * 5 + cube.boundary_tolerance
    )
    active &= cube.first[cube.rows, 72, safe_asset] <= 72 * 5 + cube.boundary_tolerance
    active &= np.isfinite(cube.opens[cube.rows, safe_entry, safe_asset])
    active &= np.isfinite(cube.opens[cube.rows, 72, safe_asset])
    active &= np.isfinite(cube.opens[cube.rows, safe_entry, 0])
    active &= np.isfinite(cube.opens[:, 72, 0])
    active &= cube.opens[cube.rows, safe_entry, safe_asset] > 0
    active &= cube.opens[cube.rows, safe_entry, 0] > 0
    return safe_asset, safe_entry, active


def component_route(cube, record: dict, delay: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    model = anchored._ridge_model(record)
    selected, active = anchored.campaign._signal(cube, model, str(record["definition"]["engine"]))
    entry = np.full(len(cube.sessions), model.decision + 1 + delay, dtype=int)
    active &= cube.first[cube.rows, entry, selected] <= entry * 5 + cube.boundary_tolerance
    active &= cube.first[cube.rows, model.exit_bar, selected] <= (
        model.exit_bar * 5 + cube.boundary_tolerance
    )
    active &= np.isfinite(cube.opens[cube.rows, entry, selected])
    active &= np.isfinite(cube.opens[cube.rows, model.exit_bar, selected])
    active &= np.isfinite(cube.opens[cube.rows, entry, 0])
    active &= np.isfinite(cube.opens[:, model.exit_bar, 0])
    active &= cube.opens[cube.rows, entry, selected] > 0
    active &= cube.opens[cube.rows, entry, 0] > 0
    return selected, entry, active


def stopped_raw(
    cube,
    selected: np.ndarray,
    entry: np.ndarray,
    active: np.ndarray,
    fixed_exit: int,
    cost: float,
    hard_stop: float,
    trailing_drawdown: float,
    minimum_holding_bars: int,
) -> tuple[object, np.ndarray, np.ndarray]:
    """Return stream, common-valid mask, and chosen exits.

    Monitoring uses only complete closes. A breach exits at the next bar open.
    """
    safe_asset = np.maximum(selected, 0)
    rows = cube.rows
    entry_price = cube.opens[rows, entry, safe_asset]
    exit_bar = np.full(len(cube.sessions), fixed_exit, dtype=int)
    peak = entry_price.copy()
    unresolved = active.copy()
    invalid = np.zeros(len(cube.sessions), dtype=bool)
    first_monitor = entry + minimum_holding_bars - 1
    for bar in range(int(first_monitor.min()), fixed_exit):
        eligible = unresolved & (bar >= first_monitor)
        complete = cube.last[rows, bar, safe_asset] >= (
            bar * 5 + 4 - cube.boundary_tolerance
        )
        close = cube.closes[rows, bar, safe_asset]
        observed = eligible & complete & np.isfinite(close) & (close > 0)
        peak[observed] = np.maximum(peak[observed], close[observed])
        breach = observed & (
            ((close / entry_price - 1.0) <= -hard_stop)
            | ((close / peak - 1.0) <= -trailing_drawdown)
        )
        if not breach.any():
            continue
        next_bar = bar + 1
        next_open_ok = (
            (cube.first[rows, next_bar, safe_asset] <= next_bar * 5 + cube.boundary_tolerance)
            & np.isfinite(cube.opens[rows, next_bar, safe_asset])
            & np.isfinite(cube.opens[:, next_bar, 0])
            & (cube.opens[rows, next_bar, safe_asset] > 0)
            & (cube.opens[:, next_bar, 0] > 0)
        )
        executable = breach & next_open_ok
        exit_bar[executable] = next_bar
        invalid |= breach & ~next_open_ok
        unresolved &= ~breach
    valid = ~invalid
    final_active = active & valid
    values = np.zeros(len(cube.sessions))
    benchmark = np.zeros(len(cube.sessions))
    values[final_active] = (
        cube.opens[rows[final_active], exit_bar[final_active], safe_asset[final_active]]
        / entry_price[final_active]
        - 1.0
        - cost
    )
    benchmark[final_active] = (
        cube.opens[rows[final_active], exit_bar[final_active], 0]
        / cube.opens[rows[final_active], entry[final_active], 0]
        - 1.0
    )
    stream = prior.v12.ReturnStream(
        values, benchmark, final_active, final_active.astype(int)
    )
    return stream, valid, exit_bar


def fixed_raw(cube, selected, entry, active, fixed_exit, cost):
    values, benchmark = np.zeros(len(cube.sessions)), np.zeros(len(cube.sessions))
    rows = cube.rows
    values[active] = (
        cube.opens[rows[active], fixed_exit, selected[active]]
        / cube.opens[rows[active], entry[active], selected[active]]
        - 1.0
        - cost
    )
    benchmark[active] = (
        cube.opens[rows[active], fixed_exit, 0]
        / cube.opens[rows[active], entry[active], 0]
        - 1.0
    )
    return prior.v12.ReturnStream(values, benchmark, active, active.astype(int))


def sleeve_weights(cube, development) -> np.ndarray:
    coefficients = {
        "sector_breadth": 1,
        "risk_asset_agreement": 1,
        "sector_dispersion": -1,
        "spy_volatility": -1,
    }
    matrix = prior._state_matrix(development, "prior_close")
    train = development.masks()["train_2022_2023"]
    means = {name: float(np.nanmean(matrix[name][train])) for name in coefficients}
    scales = {
        name: max(1e-8, float(np.nanstd(matrix[name][train]))) for name in coefficients
    }
    score = prior._state_score(
        prior._state_matrix(cube, "prior_close"), coefficients, means, scales
    )
    return np.where(np.isfinite(score) & (score >= -0.08095885648451538), 0.16, 0.0)


def build_streams(cube, development, record, models, definition):
    scenarios = ((prior.v34.STANDARD_COST, 0), (prior.v34.STRESS_COST, 0), (prior.v34.STANDARD_COST, 1))
    anchor_raw, component_raw, valids, exits = [], [], [], []
    for cost, delay in scenarios:
        anchor_selected, anchor_entry, anchor_active = anchor_route(cube, models, delay)
        component_selected, component_entry, component_active = component_route(cube, record, delay)
        stopped_anchor, anchor_valid, anchor_exit = stopped_raw(
            cube,
            anchor_selected,
            anchor_entry,
            anchor_active,
            72,
            cost,
            definition["hard_stop"],
            definition["trailing_drawdown"],
            definition["minimum_holding_bars"],
        )
        fixed_component = fixed_raw(
            cube, component_selected, component_entry, component_active, int(record["definition"]["exit"]), cost
        )
        if definition["application_mode"] == "both_sleeves":
            stopped_component, component_valid, component_exit = stopped_raw(
                cube,
                component_selected,
                component_entry,
                component_active,
                int(record["definition"]["exit"]),
                cost,
                definition["hard_stop"],
                definition["trailing_drawdown"],
                definition["minimum_holding_bars"],
            )
        else:
            stopped_component = fixed_component
            component_valid = np.ones(len(cube.sessions), dtype=bool)
            component_exit = np.full(len(cube.sessions), int(record["definition"]["exit"]), dtype=int)
        anchor_raw.append(stopped_anchor)
        component_raw.append(stopped_component)
        valids.append(anchor_valid & component_valid)
        exits.append((anchor_exit, component_exit))
    anchor_exposure = anchored.v42._exposure(anchor_raw[0].values, 15, 0.35, 0.0)
    component_exposure = anchored.v42._exposure(
        component_raw[0].values,
        int(record["definition"]["lookback"]),
        float(record["definition"]["target_volatility"]),
        0.0,
    )
    component_weight = sleeve_weights(cube, development)
    streams = []
    for index in range(3):
        common = valids[index]
        anchor = anchored.v42._scaled(anchor_raw[index], anchor_exposure)
        component = anchored.v42._scaled(component_raw[index], component_exposure)
        streams.append(
            risk.add(
                risk.scaled(anchor, (1.0 - component_weight) * common),
                risk.scaled(component, component_weight * common),
            )
        )
    return tuple(streams), tuple(valids), tuple(exits)


def observe(cube, streams):
    return {
        name: prior.v47._observe(cube, stream, True)
        for name, stream in zip(SCENARIOS, streams, strict=True)
    }


def tail(values: np.ndarray) -> float:
    return risk.tail_loss(values)


def primary(metric: dict) -> bool:
    return (
        metric["annualized_return"] >= 0.5
        and metric["max_drawdown"] < 0.2
        and metric["information_ratio"] >= 1.0
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    proposal = json.loads(PROPOSAL.read_text())
    args.output.mkdir(parents=True, exist_ok=True)
    contract = {
        "proposal_sha256": sha(PROPOSAL),
        "code_sha256": sha(Path(__file__)),
        "proposal_version": proposal["proposal_version"],
    }
    prior.v12._atomic(args.output / "contract.json", contract)
    dev = prior.v53.Cube(args.root, "alpaca", 0)
    hist = prior.v53.Cube(args.root, "historical", 0)
    record = component_record()
    models = prior.v44._fit(dev, (20, 23, 26, 29), 72)
    baseline_parts = risk.baseline_parts(dev, dev)
    hist_baseline_parts = risk.baseline_parts(hist, dev)
    baseline = tuple(risk.add(a, b) for a, b in baseline_parts)
    hist_baseline = tuple(risk.add(a, b) for a, b in hist_baseline_parts)
    base_obs, hist_base_obs = observe(dev, baseline), observe(hist, hist_baseline)
    grid = list(
        itertools.product(
            proposal["grid"]["hard_stops"],
            proposal["grid"]["trailing_drawdowns"],
            proposal["grid"]["minimum_holding_bars"],
            proposal["grid"]["application_modes"],
        )
    )
    if len(grid) != 100:
        raise RuntimeError("GRID_NOT_100")
    oos = dev.masks()["development_oos_2024_2025"]
    records, primary_flags = [], {}
    for offset, (hard_stop, trailing, minimum_holding, application_mode) in enumerate(grid):
        definition = {
            "version": proposal["first_version"] + offset,
            "hard_stop": hard_stop,
            "trailing_drawdown": trailing,
            "minimum_holding_bars": minimum_holding,
            "application_mode": application_mode,
            "trigger_clock": "complete_5min_close",
            "execution_clock": "next_5min_open",
        }
        streams, valids, exits = build_streams(dev, dev, record, models, definition)
        hist_streams, _, _ = build_streams(hist, dev, record, models, definition)
        observations, historical = observe(dev, streams), observe(hist, hist_streams)
        risks, gates, folds, starts = {}, {}, {}, {}
        for index, name in enumerate(SCENARIOS):
            metric = observations[name]["development_oos_2024_2025"]
            matched_base = risk.scaled(baseline[index], valids[index].astype(float))
            matched_metric = prior.v47._observe(dev, matched_base, True)["development_oos_2024_2025"]
            risks[name] = {
                "mdd_reduction": 1.0 - metric["max_drawdown"] / matched_metric["max_drawdown"],
                "tail_loss_reduction": 1.0
                - tail(streams[index].values[oos]) / tail(matched_base.values[oos]),
            }
            gates[f"{name}_primary"] = primary(metric)
            folds[name] = [
                metrics(streams[index].values[x], streams[index].benchmark[x], streams[index].active[x])
                for x in np.array_split(np.flatnonzero(dev.masks()["development_all"]), 5)
            ]
            starts[name] = {}
            for start in ("2022-01-01", "2023-01-01", "2024-01-01"):
                mask = dev.masks()["development_all"] & (dev.dates >= pd.Timestamp(start))
                starts[name][start] = metrics(
                    streams[index].values[mask], streams[index].benchmark[mask], streams[index].active[mask]
                )
        history = historical["standard"]["historical_2018_2020"]
        gates.update(
            {
                "risk_reduction": all(
                    item["mdd_reduction"] >= 0.2 and item["tail_loss_reduction"] >= 0.15
                    for item in risks.values()
                ),
                "four_of_five_positive_folds_all_scenarios": all(
                    sum(item["annualized_return"] > 0 for item in group) >= 4
                    for group in folds.values()
                ),
                "all_start_dates_positive_all_scenarios": all(
                    item["annualized_return"] > 0
                    for group in starts.values()
                    for item in group.values()
                ),
                "historical_positive_mdd_below_20pct": history["annualized_return"] > 0
                and history["max_drawdown"] < 0.2,
                "consumed_2026q1_above_5pct": observations["standard"]["consumed_2026q1"]["total_return"]
                >= 0.05,
            }
        )
        main_metric = observations["standard"]["development_oos_2024_2025"]
        z = main_metric["information_ratio"] * math.sqrt(max(1, main_metric["trades"]) / 252)
        bonf = min(1.0, 2 * prior.v47._normal_tail(abs(z)) * proposal["cumulative_comparison_cells"])
        gates["global_bonferroni"] = bonf < 0.05
        key = (hard_stop, trailing, minimum_holding, application_mode)
        primary_flags[key] = all(gates[f"{name}_primary"] for name in SCENARIOS)
        records.append(
            {
                "candidate_id": f"risk-v{definition['version']}-" + prior._identity(definition),
                "definition": definition,
                **observations,
                "historical_scenarios": historical,
                "risk_improvement": risks,
                "folds": folds,
                "start_dates": starts,
                "gates": gates,
                "invalid_sessions": {
                    name: int((~valid).sum()) for name, valid in zip(SCENARIOS, valids, strict=True)
                },
                "early_exits": {
                    name: {
                        "anchor": int((pair[0] < 72).sum()),
                        "component": int((pair[1] < int(record["definition"]["exit"])).sum()),
                    }
                    for name, pair in zip(SCENARIOS, exits, strict=True)
                },
                "multiple_comparison": {
                    "bonferroni_p": bonf,
                    "cumulative_cells": proposal["cumulative_comparison_cells"],
                },
                "admitted": False,
            }
        )
    values = proposal["grid"]
    for item in records:
        definition = item["definition"]
        center = (
            definition["hard_stop"],
            definition["trailing_drawdown"],
            definition["minimum_holding_bars"],
            definition["application_mode"],
        )
        indices = tuple(
            values[name].index(value)
            for name, value in zip(
                ("hard_stops", "trailing_drawdowns", "minimum_holding_bars", "application_modes"),
                center,
                strict=True,
            )
        )
        neighbors = []
        for key, flag in primary_flags.items():
            other = tuple(
                values[name].index(value)
                for name, value in zip(
                    ("hard_stops", "trailing_drawdowns", "minimum_holding_bars", "application_modes"),
                    key,
                    strict=True,
                )
            )
            if sum(abs(a - b) for a, b in zip(indices, other, strict=True)) <= 1:
                neighbors.append(flag)
        share = sum(neighbors) / len(neighbors)
        item["parameter_neighbor_primary_share"] = share
        item["gates"]["parameter_neighbor_70pct_primary"] = share >= 0.7
        pre = all(v for k, v in item["gates"].items() if k != "global_bonferroni")
        item["pre_native_overlay_null_pass"] = pre
        item["native_null_status"] = "NEEDS_NATIVE_OVERLAY_NULL" if pre else "NOT_RUN_PRE_NULL_FAILED"
    ranking = sorted(
        records,
        key=lambda item: (
            all(item["gates"][f"{name}_primary"] for name in SCENARIOS),
            item["gates"]["risk_reduction"],
            item["gates"]["historical_positive_mdd_below_20pct"],
            min(x["mdd_reduction"] for x in item["risk_improvement"].values()),
            item["standard"]["development_oos_2024_2025"]["annualized_return"],
        ),
        reverse=True,
    )
    result = {
        "status": "COMPLETE",
        "versions": [proposal["first_version"], proposal["last_version"]],
        "hypotheses": len(records),
        "elapsed_seconds": time.perf_counter() - started,
        "contract": contract,
        "baseline": base_obs,
        "historical_baseline": hist_base_obs,
        "records": records,
        "ranked_candidate_ids": [item["candidate_id"] for item in ranking],
        "pre_native_overlay_null_passes": sum(item["pre_native_overlay_null_pass"] for item in records),
        "admissions": 0,
    }
    prior.v12._atomic(args.output / "result.json", result)
    print(
        json.dumps(
            {
                "status": result["status"],
                "hypotheses": result["hypotheses"],
                "pre_null_passes": result["pre_native_overlay_null_passes"],
                "best": ranking[0]["candidate_id"],
                "elapsed_seconds": round(result["elapsed_seconds"], 3),
            }
        )
    )


if __name__ == "__main__":
    main()
