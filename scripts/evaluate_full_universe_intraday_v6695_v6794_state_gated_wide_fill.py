"""v6695-v6794 prior-close state-gated disjoint wide-fill campaign."""

from __future__ import annotations

import argparse
import itertools
import json
import math
import time
from pathlib import Path

import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v39_multifactor_regime_gate as v39
import evaluate_full_universe_intraday_v47_score_slope as v47
import evaluate_full_universe_intraday_v4170_v4269_dual_parent_routing as state
import evaluate_full_universe_intraday_v6595_v6694_disjoint_wide_cash_fill as prior
import numpy as np
import pandas as pd

from us_intraday_lab.fast_intraday_research import metrics

FIRST_VERSION = 6695
LAST_VERSION = 6794
PRIOR_COMPARISON_CELLS = 255_555
QUANTILES = (0.20, 0.35, 0.50, 0.65, 0.80)
ORIENTATIONS = ("fill_on_high", "fill_on_low")
CORE_LOW_DISPERSION_TREND = dict(state.STATE_FAMILIES["low_dispersion_trend"])
CORE_OVERSOLD_REPAIR = dict(state.STATE_FAMILIES["oversold_repair"])
FILL_PARENTS = (
    "lev-v42t-9f96beaddb33b2fb",
    "lev-v42t-07566ced3a358a4f",
    "lev-v42t-6cc68a5a8184492a",
    "lev-v42t-336ed49b282f9ef2",
    "lev-v42t-2ea705297ea82538",
    "lev-v42t-0ff8216ae0c8c1c5",
    "lev-v42t-7fa628a0a122d7a1",
    "lev-v42t-45bc223e34db25bd",
    "lev-v42t-c3c1886e4da2d7e6",
    "lev-v42t-e9a2127d4c32fc73",
)
FILL_WEIGHTS = np.asarray(
    (
        0.05845093687626459,
        0.1239108920700459,
        0.08960936364903266,
        0.06360053831757795,
        0.1625163076681646,
        0.06204975555170996,
        0.15646598251858898,
        0.10603584977992435,
        0.10123395571436643,
        0.07612641785432452,
    )
)
EXTRA_COMPONENT_BUILDER = None
EXTRA_COMPONENT_DEFINITION = None


def _combine_extra(streams, extras):
    if extras is None:
        return streams
    return tuple(
        v34.v12.ReturnStream(
            base.values + extra.values,
            base.benchmark + extra.benchmark,
            base.active | extra.active,
            base.component_trades + extra.component_trades,
        )
        for base, extra in zip(streams, extras, strict=True)
    )


def specifications():
    return list(itertools.product(state.STATE_FAMILIES, QUANTILES, ORIENTATIONS))


def _disjoint_gated(base, fill, allowed):
    use_fill = (~base.active) & fill.active & allowed
    return v34.v12.ReturnStream(
        np.where(base.active, base.values, np.where(use_fill, fill.values, 0.0)),
        np.where(base.active, base.benchmark, np.where(use_fill, fill.benchmark, 0.0)),
        base.active | use_fill,
        base.component_trades + np.where(use_fill, fill.component_trades, 0),
    )


def _allowed(cube, model, orientation):
    score = state._score(cube, model)
    finite = np.isfinite(score)
    high = finite & (score >= model["threshold"])
    return high if orientation == "fill_on_high" else finite & (~high)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if prior.parent._sha(args.source) != prior.SOURCE_SHA256:
        raise RuntimeError("V42_SOURCE_HASH_CHANGED")
    prior.cash._configure()
    if len(specifications()) != 100 or not np.isclose(FILL_WEIGHTS.sum(), 1.0):
        raise RuntimeError("STATE_GATED_WIDE_FILL_PREREGISTRATION_MISMATCH")
    started = time.perf_counter()
    source = json.loads(args.source.read_text(encoding="utf-8"))
    source_map = {item["candidate_id"]: item for item in source["records"]}
    base_ids = tuple(
        dict.fromkeys(
            (
                prior.route.MODERN_PARENT,
                prior.route.TRANSFER_PARENT,
                prior.cash.FALLBACK_PARENT,
            )
        )
    )
    required = tuple(dict.fromkeys((*base_ids, *FILL_PARENTS)))
    if any(item not in source_map for item in required):
        raise RuntimeError("FROZEN_PARENT_MISSING")
    development = v34.Cube(args.root, "alpaca", 0)
    historical = v34.Cube(args.root, "historical", 0)
    development_state = prior.parent.cross.Cube(args.root, "alpaca", 0)
    historical_state = prior.parent.cross.Cube(args.root, "historical", 0)
    models = {
        item: v39._models(development, [source_map[item]["definition"]["strategy"]])[0]
        for item in required
    }
    development_parents = {
        item: prior.parent._parent_streams(development, source_map[item], models[item])
        for item in required
    }
    historical_parents = {
        item: prior.parent._parent_streams(historical, source_map[item], models[item])
        for item in required
    }
    core_model = state._fit_state(development_state, CORE_LOW_DISPERSION_TREND, 0.20)
    override_model = state._fit_state(development_state, CORE_OVERSOLD_REPAIR, 0.35)
    _, transfer_state = prior.route._base_state(development_state, core_model, override_model)
    gate_model = prior.route._fit_gate(
        development,
        development_parents[prior.route.TRANSFER_PARENT][0],
        transfer_state,
        prior.route.FACTOR_SETS[prior.BASE_FAMILY],
        prior.BASE_QUANTILE,
        prior.BASE_ALPHA,
    )
    dev_base = prior._base_streams(
        development,
        development_state,
        {item: development_parents[item] for item in base_ids},
        core_model,
        override_model,
        gate_model,
    )
    hist_base = prior._base_streams(
        historical,
        historical_state,
        {item: historical_parents[item] for item in base_ids},
        core_model,
        override_model,
        gate_model,
    )
    extra_dev, extra_hist = (None, None)
    if EXTRA_COMPONENT_BUILDER is not None:
        extra_dev, extra_hist = EXTRA_COMPONENT_BUILDER(
            development,
            historical,
            development_state,
            historical_state,
            core_model,
            override_model,
        )
    dev_fill = tuple(
        prior.wide.campaign._combine(
            [development_parents[item][scenario] for item in FILL_PARENTS], FILL_WEIGHTS
        )
        for scenario in range(3)
    )
    hist_fill = tuple(
        prior.wide.campaign._combine(
            [historical_parents[item][scenario] for item in FILL_PARENTS], FILL_WEIGHTS
        )
        for scenario in range(3)
    )
    cells = []
    for offset, (family, quantile, orientation) in enumerate(specifications()):
        model = state._fit_state(development_state, state.STATE_FAMILIES[family], quantile)
        allowed = _allowed(development_state, model, orientation)
        streams = tuple(
            _disjoint_gated(base, fill, allowed)
            for base, fill in zip(dev_base, dev_fill, strict=True)
        )
        streams = _combine_extra(streams, extra_dev)
        observations = tuple(v47._observe(development, stream, True) for stream in streams)
        cells.append(
            {
                "version": FIRST_VERSION + offset,
                "family": family,
                "quantile": quantile,
                "orientation": orientation,
                "model": model,
                "streams": streams,
                "observations": observations,
                "primary": all(prior._primary(item) for item in observations),
            }
        )
    total_cells = PRIOR_COMPARISON_CELLS + len(cells)
    folds = np.array_split(np.flatnonzero(development.masks()["development_all"]), 5)
    results = []
    for cell in cells:
        historical_allowed = _allowed(historical_state, cell["model"], cell["orientation"])
        historical_streams = tuple(
            _disjoint_gated(base, fill, historical_allowed)
            for base, fill in zip(hist_base, hist_fill, strict=True)
        )
        historical_streams = _combine_extra(historical_streams, extra_hist)
        historical_obs = tuple(
            v47._observe(historical, stream, True)["historical_2018_2020"]
            for stream in historical_streams
        )
        streams, observations = cell["streams"], cell["observations"]
        fold_metrics = {
            name: [
                metrics(stream.values[index], stream.benchmark[index], stream.active[index])
                for index in folds
            ]
            for name, stream in zip(
                ("standard", "cost_18bp", "delay_5min_9bp"), streams, strict=True
            )
        }
        starts = {}
        for start_date in ("2022-01-01", "2023-01-01", "2024-01-01"):
            mask = development.masks()["development_all"] & (
                development.dates >= pd.Timestamp(start_date)
            )
            starts[start_date] = metrics(
                streams[0].values[mask], streams[0].benchmark[mask], streams[0].active[mask]
            )
        q_index = QUANTILES.index(cell["quantile"])
        neighbors = [
            item
            for item in cells
            if item["family"] == cell["family"]
            and item["orientation"] == cell["orientation"]
            and abs(QUANTILES.index(item["quantile"]) - q_index) <= 1
        ]
        neighborhood = sum(item["primary"] for item in neighbors) / len(neighbors)
        oos = observations[0]["development_oos_2024_2025"]
        z_score = float(oos["information_ratio"]) * math.sqrt(max(1, int(oos["trades"])) / 252)
        bonferroni = min(1.0, 2.0 * v47._normal_tail(abs(z_score)) * total_cells)
        gates = {
            "standard_primary": prior._primary(observations[0]),
            "cost_18bp_primary": prior._primary(observations[1]),
            "delay_5min_primary": prior._primary(observations[2]),
            "four_of_five_positive_folds_all_scenarios": all(
                sum(float(item["annualized_return"]) > 0 for item in values) >= 4
                for values in fold_metrics.values()
            ),
            "all_start_dates_positive": all(
                float(item["annualized_return"]) > 0 for item in starts.values()
            ),
            "historical_15pct_mdd_below_20pct_all_scenarios": all(
                float(item["annualized_return"]) >= 0.15 and float(item["max_drawdown"]) < 0.20
                for item in historical_obs
            ),
            "parameter_neighborhood_70pct_primary": neighborhood >= 0.70,
            "consumed_2026q1_above_5pct": float(observations[0]["consumed_2026q1"]["total_return"])
            > 0.05,
            "consumed_2026_total_above_5pct": float(
                observations[0]["consumed_2026_all"]["total_return"]
            )
            > 0.05,
            "cumulative_bonferroni_5pct": bonferroni < 0.05,
        }
        model = cell["model"]
        definition = {
            "version": cell["version"],
            "mechanism": "v6626_prior_close_state_gated_disjoint_fill",
            "state_family": cell["family"],
            "state_quantile": cell["quantile"],
            "orientation": cell["orientation"],
            "fill_parents": FILL_PARENTS,
            "fill_weights": FILL_WEIGHTS.tolist(),
            "extra_component": EXTRA_COMPONENT_DEFINITION,
        }
        results.append(
            {
                "candidate_id": f"lev-v{cell['version']}-" + prior._identity(definition),
                "definition": definition,
                "state_model": {
                    "names": model["names"],
                    "mean": model["mean"].tolist(),
                    "scale": model["scale"].tolist(),
                    "direction": model["direction"].tolist(),
                    "threshold": model["threshold"],
                },
                "standard": observations[0],
                "cost_18bp": observations[1],
                "delay_5min_9bp": observations[2],
                "historical_scenarios": dict(
                    zip(
                        ("standard", "cost_18bp", "delay_5min_9bp"),
                        historical_obs,
                        strict=True,
                    )
                ),
                "development_folds": fold_metrics,
                "start_date_stress": starts,
                "neighbor_primary_share": neighborhood,
                "multiple_comparison": {
                    "total_cells": total_cells,
                    "z_score": z_score,
                    "bonferroni_p": bonferroni,
                },
                "gates": gates,
                "strict_pre_factory_null_pass": all(gates.values()),
            }
        )
    results.sort(
        key=lambda item: prior._rank((item["standard"], item["cost_18bp"], item["delay_5min_9bp"])),
        reverse=True,
    )
    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "version_range": [FIRST_VERSION, LAST_VERSION],
        "evaluated_cells": len(results),
        "comparison_cells": total_cells,
        "elapsed_seconds": time.perf_counter() - started,
        "strict_pre_factory_null_passes": sum(
            item["strict_pre_factory_null_pass"] for item in results
        ),
        "records": results,
    }
    v34.v12._atomic(args.output, payload)
    print(
        json.dumps(
            {
                "status": payload["status"],
                "evaluated_cells": payload["evaluated_cells"],
                "strict_pre_factory_null_passes": payload["strict_pre_factory_null_passes"],
                "best": results[0]["candidate_id"],
                "elapsed_seconds": payload["elapsed_seconds"],
            }
        )
    )


if __name__ == "__main__":
    main()
