"""v7695-v7794 independent midday cross-sectional continuation campaign."""

from __future__ import annotations

import math

import evaluate_full_universe_intraday_v550_v649_state_gated_reversal as campaign
import evaluate_full_universe_intraday_v5970_v6069_sector_flow_leadership as sector
import numpy as np
import pandas as pd

from us_intraday_lab.fast_intraday_research import metrics

FIRST_VERSION = 7695
LAST_VERSION = 7794
PRIOR_COMPARISON_CELLS = 256_555
FAMILIES = (
    ("relative_sector_flow", ("relative_return", "sector_signed_flow_breadth", "sector_return_flow_agreement"), (1, 1, 1)),
    ("efficient_relative_strength", ("relative_return", "path_efficiency", "sector_path_efficiency_breadth"), (1, 1, 1)),
    ("growth_flow_leadership", ("relative_return", "growth_minus_defensive_return", "growth_minus_defensive_flow"), (1, 1, 1)),
    ("broadening_continuation", ("current_return", "sector_breadth_acceleration", "sector_signed_flow_breadth"), (1, 1, 1)),
    ("quiet_relative_breakout", ("relative_return", "recent_volatility_ratio", "sector_volatility_contraction"), (1, -1, -1)),
    ("flow_persistent_leader", ("relative_return", "signed_volume_imbalance", "sector_return_flow_agreement"), (1, 1, 1)),
    ("vwap_leader_confirmation", ("vwap_distance", "relative_return", "sector_path_efficiency_breadth"), (1, 1, 1)),
    ("rank_flow_leadership", ("current_rank", "growth_minus_defensive_flow", "sector_leadership_spread"), (1, 1, 1)),
    ("contraction_broadening", ("return_acceleration", "recent_volatility_ratio", "sector_breadth_acceleration", "sector_volatility_contraction"), (1, -1, 1, -1)),
    ("balanced_midday_leader", ("current_return", "relative_return", "path_efficiency", "signed_volume_imbalance", "sector_signed_flow_breadth", "sector_return_flow_agreement", "sector_breadth_acceleration", "growth_minus_defensive_flow"), (1, 1, 1, 1, 1, 1, 1, 1)),
)
SCHEDULES = ((23, 47), (29, 53), (35, 59), (41, 65), (47, 72))
STATE_MODES = ("unfiltered", "orderly_rebound_cash_filter")


def _historical_streams(historical, selected):
    parameters, model = selected["parameters"], selected["model"]
    streams = []
    for cost, delay in ((campaign.prior.v34.STANDARD_COST, 0), (campaign.prior.v34.STRESS_COST, 0), (campaign.prior.v34.STANDARD_COST, 1)):
        raw = campaign.prior._rule_raw(historical, parameters, np.asarray(model["mean"]), np.asarray(model["scale"]), float(parameters["score_threshold"]), cost, delay)
        if parameters["state_mode"] != "unfiltered":
            score = campaign._state_score(historical, int(parameters["decision"]), model["state_means"], model["state_scales"])
            raw = campaign.prior._mask_stream(raw, np.isfinite(score) & (score >= float(parameters["state_threshold"])))
        streams.append(campaign._scale((raw,), float(parameters["target_volatility"]), int(parameters["lookback"]))[0])
    return tuple(streams)


def _record(development, historical, version, cells, selected, total_cells):
    observations = tuple(campaign.prior.v47._observe(development, stream, True) for stream in selected["streams"])
    historical_obs = tuple(campaign.prior.v47._observe(historical, stream, True)["historical_2018_2020"] for stream in _historical_streams(historical, selected))
    folds = np.array_split(np.flatnonzero(development.masks()["development_all"]), 5)
    fold_metrics = {name: [metrics(stream.values[index], stream.benchmark[index], stream.active[index]) for index in folds] for name, stream in zip(("standard", "cost_18bp", "delay_5min_9bp"), selected["streams"], strict=True)}
    starts = {}
    for start in ("2022-01-01", "2023-01-01", "2024-01-01"):
        mask = development.masks()["development_all"] & (development.dates >= pd.Timestamp(start))
        stream = selected["streams"][0]
        starts[start] = metrics(stream.values[mask], stream.benchmark[mask], stream.active[mask])
    neighborhood = campaign._neighbor_share(cells, selected)
    oos = observations[0]["development_oos_2024_2025"]
    z_score = float(oos["information_ratio"]) * math.sqrt(max(1, int(oos["trades"])) / 252)
    bonferroni = min(1.0, 2.0 * campaign.prior.v47._normal_tail(abs(z_score)) * total_cells)
    gates = {
        "standard_primary": campaign._primary(observations[0]),
        "cost_18bp_primary": campaign._primary(observations[1]),
        "delay_5min_primary": campaign._primary(observations[2]),
        "four_of_five_positive_folds_all_scenarios": all(sum(float(item["annualized_return"]) > 0 for item in values) >= 4 for values in fold_metrics.values()),
        "all_start_dates_positive": all(float(item["annualized_return"]) > 0 for item in starts.values()),
        "historical_15pct_mdd_below_20pct_all_scenarios": all(float(item["annualized_return"]) >= 0.15 and float(item["max_drawdown"]) < 0.20 for item in historical_obs),
        "parameter_neighborhood_70pct_primary": neighborhood >= 0.70,
        "consumed_2026q1_above_5pct": float(observations[0]["consumed_2026q1"]["total_return"]) > 0.05,
        "consumed_2026_total_above_5pct": float(observations[0]["consumed_2026_all"]["total_return"]) > 0.05,
        "cumulative_bonferroni_5pct": bonferroni < 0.05,
    }
    definition = {"version": version, **selected["parameters"]}
    return {
        "candidate_id": f"lev-v{version}-" + campaign.prior._identity(definition), "definition": definition, "model": selected["model"], "development_rank": list(selected["rank"]),
        "standard": observations[0], "cost_18bp": observations[1], "delay_5min_9bp": observations[2],
        "historical_scenarios": {"standard": historical_obs[0], "cost_18bp": historical_obs[1], "delay_5min_9bp": historical_obs[2]},
        "development_folds": fold_metrics, "start_date_stress": starts, "neighbor_primary_share": neighborhood,
        "multiple_comparison": {"total_cells": total_cells, "z_score": z_score, "bonferroni_p": bonferroni}, "gates": gates,
        "pre_factory_null_pass": all(gates.values()), "all_reference_gates_pass": all(gates.values()),
    }


def _configure() -> None:
    campaign.FIRST_VERSION = FIRST_VERSION
    campaign.LAST_VERSION = LAST_VERSION
    campaign.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    campaign.FAMILIES = FAMILIES
    campaign.SCHEDULES = SCHEDULES
    campaign.STATE_MODES = STATE_MODES
    campaign.prior.v53.Cube = sector.SectorFlowLeadershipCube
    campaign._record = _record


if __name__ == "__main__":
    _configure()
    campaign.main()
