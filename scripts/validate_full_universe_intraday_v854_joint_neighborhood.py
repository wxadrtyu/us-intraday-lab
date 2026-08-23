"""v854 joint weight, split and state-threshold neighborhood for v798."""

from __future__ import annotations

import argparse
import itertools
import json
import time
from pathlib import Path

import evaluate_full_universe_intraday_v146_v245_anchored_ensembles as anchored
import evaluate_full_universe_intraday_v248_v347_mechanism_campaign as prior
import evaluate_full_universe_intraday_v753_v852_dual_component_routing as campaign
import numpy as np

TOTAL_WEIGHTS = (0.08, 0.09, 0.10)
V247_SHARES = (0.0, 0.10, 0.25)
STATE_QUANTILES = (0.10, 0.20, 0.30, 0.35)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--component-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--candidate", default="lev-v798-d0612cdc630bb224")
    parser.add_argument("--validation-version", type=int, default=854)
    args = parser.parse_args()
    started = time.perf_counter()
    development = prior.v53.Cube(args.root, "alpaca", 0)
    historical = prior.v53.Cube(args.root, "historical", 0)
    models = prior.v44._fit(development, (20, 23, 26, 29), 72)
    anchor_dev = anchored._v45_streams(development, models)
    anchor_hist = anchored._v45_streams(historical, models)[0]
    records = {
        name: campaign._component_record(args.component_dir, candidate_id)
        for name, candidate_id in campaign.COMPONENT_IDS.items()
    }
    component_dev = {
        name: anchored._component_streams(development, record) for name, record in records.items()
    }
    component_hist = {
        name: anchored._component_streams(historical, record)[0]
        for name, record in records.items()
    }
    definition = (
        json.loads(args.source.read_text(encoding="utf-8"))["records"][0]["definition"]
        if args.source is not None
        else {
            "state_clock": "prior_close",
            "state_coefficients": campaign.ROUTING_MODES[1][2],
        }
    )
    coefficients = dict(definition["state_coefficients"])
    train = development.masks()["train_2022_2023"]
    dev_matrix = prior._state_matrix(development, str(definition["state_clock"]))
    hist_matrix = prior._state_matrix(historical, str(definition["state_clock"]))
    means = {name: float(np.nanmean(dev_matrix[name][train])) for name in coefficients}
    scales = {
        name: max(1e-8, float(np.nanstd(dev_matrix[name][train]))) for name in coefficients
    }
    dev_score = prior._state_score(dev_matrix, coefficients, means, scales)
    hist_score = prior._state_score(hist_matrix, coefficients, means, scales)
    finite_train = dev_score[train & np.isfinite(dev_score)]
    cells = []
    for total_weight, share, quantile in itertools.product(
        TOTAL_WEIGHTS, V247_SHARES, STATE_QUANTILES
    ):
        threshold = float(np.quantile(finite_train, quantile))
        dev_allowed = np.isfinite(dev_score) & (dev_score >= threshold)
        hist_allowed = np.isfinite(hist_score) & (hist_score >= threshold)
        streams = tuple(
            campaign._blend(
                anchor,
                campaign._route(v247, dev_allowed),
                campaign._route(v449, dev_allowed),
                total_weight=total_weight,
                v247_share=share,
            )
            for anchor, v247, v449 in zip(
                anchor_dev, component_dev["v247"], component_dev["v449"], strict=True
            )
        )
        observations = [prior.v47._observe(development, stream, True) for stream in streams]
        historical_stream = campaign._blend(
            anchor_hist,
            campaign._route(component_hist["v247"], hist_allowed),
            campaign._route(component_hist["v449"], hist_allowed),
            total_weight=total_weight,
            v247_share=share,
        )
        historical_obs = prior.v47._observe(historical, historical_stream, True)[
            "historical_2018_2020"
        ]
        standard = observations[0]
        gates = {
            "standard_primary": campaign._primary(observations[0]),
            "cost_18bp_primary": campaign._primary(observations[1]),
            "delay_5min_primary": campaign._primary(observations[2]),
            "historical_positive_mdd_below_20pct": (
                float(historical_obs["annualized_return"]) > 0
                and float(historical_obs["max_drawdown"]) < 0.20
            ),
            "consumed_2026q1_above_5pct": float(
                standard["consumed_2026q1"]["total_return"]
            )
            > 0.05,
            "consumed_2026_all_above_5pct": float(
                standard["consumed_2026_all"]["total_return"]
            )
            > 0.05,
        }
        cells.append(
            {
                "component_total_weight": total_weight,
                "v247_component_share": share,
                "state_quantile": quantile,
                "oos_annualized_return": standard["development_oos_2024_2025"][
                    "annualized_return"
                ],
                "oos_max_drawdown": standard["development_oos_2024_2025"]["max_drawdown"],
                "oos_information_ratio": standard["development_oos_2024_2025"][
                    "information_ratio"
                ],
                "cost_18bp_annualized_return": observations[1]["development_oos_2024_2025"][
                    "annualized_return"
                ],
                "delay_5min_annualized_return": observations[2]["development_oos_2024_2025"][
                    "annualized_return"
                ],
                "historical_annualized_return": historical_obs["annualized_return"],
                "historical_max_drawdown": historical_obs["max_drawdown"],
                "consumed_2026q1_total_return": standard["consumed_2026q1"]["total_return"],
                "consumed_2026_total_return": standard["consumed_2026_all"]["total_return"],
                "gates": gates,
                "passed": all(gates.values()),
            }
        )
    pass_share = sum(cell["passed"] for cell in cells) / len(cells)
    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "version": args.validation_version,
        "candidate_id": args.candidate,
        "evaluated_cells": len(cells),
        "passed_cells": sum(cell["passed"] for cell in cells),
        "joint_neighborhood_pass_share": pass_share,
        "threshold": 0.70,
        "passed": pass_share >= 0.70,
        "elapsed_seconds": time.perf_counter() - started,
        "cells": cells,
    }
    prior.v12._atomic(args.output, payload)
    print(json.dumps({key: value for key, value in payload.items() if key != "cells"}, indent=2))


if __name__ == "__main__":
    main()
