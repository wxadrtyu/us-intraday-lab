"""Validate v11098 branch timing and daily forward-plan parity."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v39_multifactor_regime_gate as v39
import evaluate_full_universe_intraday_v5970_v6069_sector_flow_leadership as sector
import evaluate_full_universe_intraday_v11006_v11105_branch_causal as branch
import numpy as np

from us_intraday_lab.paper.v10824 import assemble_forward_plan, routed_anchor

CANDIDATE_ID = "lev-v11098-2ddc1d07c9cfe31e"
SELECTION_RANGE = [11006, 11105]
CAMPAIGN_CONFIGURE = branch._configure


def validate(root: Path, source_path: Path, selection_path: Path) -> dict:
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    candidates = [item for item in selection["records"] if item["candidate_id"] == CANDIDATE_ID]
    if selection.get("version_range") != SELECTION_RANGE or len(candidates) != 1:
        raise RuntimeError("V11098_PARITY_SELECTION_CHANGED")
    definition = candidates[0]["definition"]
    CAMPAIGN_CONFIGURE()
    campaign = branch.boundary.logical.clock.parent.parent.sparse_veto.campaign
    sparse_veto = branch.boundary.logical.clock.parent.parent.sparse_veto
    campaign.base.prior.cash._configure()
    source = json.loads(source_path.read_text(encoding="utf-8"))
    source_map = {item["candidate_id"]: item for item in source["records"]}
    route = campaign.base.prior.route
    fallback_id = campaign.base.prior.cash.FALLBACK_PARENT
    base_ids = tuple(dict.fromkeys((route.MODERN_PARENT, route.TRANSFER_PARENT, fallback_id)))
    required = tuple(dict.fromkeys((*base_ids, *campaign.base.FILL_PARENTS)))
    cube = v34.Cube(root, "alpaca", 0)
    state = campaign.base.prior.parent.cross.Cube(root, "alpaca", 0)
    factors = sector.SectorFlowLeadershipCube(root, "alpaca", 0)
    models = {
        item: v39._models(cube, [source_map[item]["definition"]["strategy"]])[0]
        for item in required
    }
    parents = {
        item: campaign.base.prior.parent._parent_streams(cube, source_map[item], models[item])
        for item in required
    }
    core = campaign.base.state._fit_state(state, campaign.base.CORE_LOW_DISPERSION_TREND, 0.20)
    override = campaign.base.state._fit_state(state, campaign.base.CORE_OVERSOLD_REPAIR, 0.35)
    modern_state, transfer_state = route._base_state(state, core, override)
    transfer_gate = route._fit_gate(
        cube,
        parents[route.TRANSFER_PARENT][0],
        transfer_state,
        route.FACTOR_SETS[campaign.base.prior.BASE_FAMILY],
        campaign.base.prior.BASE_QUANTILE,
        campaign.base.prior.BASE_ALPHA,
    )
    transfer_score = route._score(cube, transfer_gate)
    transfer_allowed = np.isfinite(transfer_score) & (
        transfer_score >= transfer_gate["threshold"]
    )
    use_transfer = (~modern_state) & transfer_allowed
    fill_placeholder = campaign.base.state._fit_state(
        state, campaign.base.state.STATE_FAMILIES["high_vol_recovery"], 0.20
    )
    expected_late = campaign._route(
        cube, state, parents, core, override, transfer_gate, fill_placeholder
    )[0]
    fill_model = sparse_veto._fill_model
    if fill_model is None:
        raise RuntimeError("V11098_FILL_MODEL_NOT_FITTED")
    fill_allowed = campaign.base._allowed(
        state, fill_model, sparse_veto.FROZEN_ORIENTATION
    )

    modern_late = branch._late_by_early[id(parents[route.MODERN_PARENT][0])]
    fallback_late = branch._late_by_early[id(parents[fallback_id][0])]
    anchor_values, anchor_active = routed_anchor(
        modern_state=modern_state,
        transfer_allowed=transfer_allowed,
        modern_values=modern_late.values,
        modern_active=modern_late.active,
        transfer_values=parents[route.TRANSFER_PARENT][0].values,
        transfer_active=parents[route.TRANSFER_PARENT][0].active,
        fallback_values=fallback_late.values,
        fallback_active=fallback_late.active,
    )
    early_fill_values = sum(
        weight * parents[parent_id][0].values
        for parent_id, weight in zip(
            campaign.base.FILL_PARENTS, campaign.base.FILL_WEIGHTS, strict=True
        )
    )
    late_fill_values = sum(
        weight * branch._late_by_early[id(parents[parent_id][0])].values
        for parent_id, weight in zip(
            campaign.base.FILL_PARENTS, campaign.base.FILL_WEIGHTS, strict=True
        )
    )
    early_fill_active = np.logical_or.reduce(
        [parents[parent_id][0].active for parent_id in campaign.base.FILL_PARENTS]
    )
    late_fill_active = np.logical_or.reduce(
        [
            branch._late_by_early[id(parents[parent_id][0])].active
            for parent_id in campaign.base.FILL_PARENTS
        ]
    )
    fill_values = np.where(use_transfer, early_fill_values, late_fill_values)
    fill_active = np.where(use_transfer, early_fill_active, late_fill_active)
    opening = branch.boundary.logical.clock.parent.parent._opening_by_late_stream[
        id(expected_late)
    ]
    gate = campaign.quality._fit(
        factors,
        expected_late,
        expected_late.active,
        campaign.FACTOR_SETS[definition["factor_set"]],
        float(definition["score_quantile"]),
        float(definition["ridge_alpha"]),
    )
    gate_score = campaign.quality._score(factors, gate)
    outer_allowed = np.isfinite(gate_score) & (gate_score >= gate["threshold"])
    expected = campaign.STREAM_TRANSFORM(expected_late, outer_allowed)
    actual = assemble_forward_plan(
        opening_values=opening.values,
        opening_active=opening.active,
        anchor_values=anchor_values,
        anchor_active=anchor_active,
        fill_values=fill_values,
        fill_active=fill_active,
        fill_allowed=fill_allowed,
        outer_allowed=outer_allowed,
        low_exposure=branch.boundary.logical.clock.parent.parent.LOW_EXPOSURE,
    )
    maximum_error = float(np.max(np.abs(expected.values - actual.values)))
    active_mismatches = int(np.count_nonzero(expected.active != actual.active))
    route_clock_passed = (
        branch.EARLY_MINIMUM_ENTRY_BAR > 2
        and branch.LATE_MINIMUM_ENTRY_BAR > 23
        and np.all((~use_transfer) | (~modern_state))
    )
    passed = maximum_error <= 1e-12 and active_mismatches == 0 and route_clock_passed
    return {
        "schema_version": "1.0.0",
        "status": "COMPLETE" if passed else "FAILED",
        "candidate_id": CANDIDATE_ID,
        "sessions": len(cube.sessions),
        "maximum_absolute_daily_return_error": maximum_error,
        "active_session_mismatches": active_mismatches,
        "transfer_route_sessions": int(np.count_nonzero(use_transfer)),
        "modern_or_fallback_route_sessions": int(np.count_nonzero(~use_transfer)),
        "early_fill_minimum_entry_bar": branch.EARLY_MINIMUM_ENTRY_BAR,
        "late_fill_minimum_entry_bar": branch.LATE_MINIMUM_ENTRY_BAR,
        "route_clock_causality_passed": bool(route_clock_passed),
        "daily_values_sha256": hashlib.sha256(
            np.asarray(actual.values, dtype="<f8").tobytes()
        ).hexdigest(),
        "passed": bool(passed),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = validate(args.root, args.source, args.selection)
    v34.v12._atomic(args.output, result)
    print(json.dumps(result))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
