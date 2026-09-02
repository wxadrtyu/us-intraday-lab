"""Prove the independent v10824 forward assembler matches the research stream."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v39_multifactor_regime_gate as v39
import evaluate_full_universe_intraday_v5970_v6069_sector_flow_leadership as sector
import evaluate_full_universe_intraday_v10805_v10904_bar5_and_boundary as boundary
import numpy as np

from us_intraday_lab.paper.v10824 import CANDIDATE_ID, assemble_forward_plan, routed_anchor


def validate(root: Path, source_path: Path, selection_path: Path) -> dict:
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    selected = [item for item in selection["records"] if item["candidate_id"] == CANDIDATE_ID]
    if selection.get("status") != "COMPLETE" or len(selected) != 1:
        raise RuntimeError("V10824_PARITY_SELECTION_CHANGED")
    definition = selected[0]["definition"]

    boundary._configure()
    campaign = boundary.logical.clock.parent.parent.sparse_veto.campaign
    campaign.base.prior.cash._configure()
    if campaign.base.prior.parent._sha(source_path) != campaign.base.prior.SOURCE_SHA256:
        raise RuntimeError("V10824_PARITY_SOURCE_CHANGED")
    source = json.loads(source_path.read_text(encoding="utf-8"))
    source_map = {item["candidate_id"]: item for item in source["records"]}
    route = campaign.base.prior.route
    base_ids = tuple(
        dict.fromkeys((route.MODERN_PARENT, route.TRANSFER_PARENT, campaign.base.prior.cash.FALLBACK_PARENT))
    )
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
    fallback_id = campaign.base.prior.cash.FALLBACK_PARENT
    anchor_values, anchor_active = routed_anchor(
        modern_state=modern_state,
        transfer_allowed=transfer_allowed,
        modern_values=parents[route.MODERN_PARENT][0].values,
        modern_active=parents[route.MODERN_PARENT][0].active,
        transfer_values=parents[route.TRANSFER_PARENT][0].values,
        transfer_active=parents[route.TRANSFER_PARENT][0].active,
        fallback_values=parents[fallback_id][0].values,
        fallback_active=parents[fallback_id][0].active,
    )
    fill_values = sum(
        weight * parents[parent_id][0].values
        for parent_id, weight in zip(
            campaign.base.FILL_PARENTS, campaign.base.FILL_WEIGHTS, strict=True
        )
    )
    fill_active = np.logical_or.reduce(
        [parents[parent_id][0].active for parent_id in campaign.base.FILL_PARENTS]
    )
    sparse_veto = boundary.logical.clock.parent.parent.sparse_veto
    placeholder = campaign.base.state._fit_state(
        state, campaign.base.state.STATE_FAMILIES["high_vol_recovery"], 0.20
    )
    late = campaign._route(cube, state, parents, core, override, transfer_gate, placeholder)[0]
    fill_state_model = sparse_veto._fill_model
    if fill_state_model is None:
        raise RuntimeError("V10824_PARITY_FILL_MODEL_NOT_FITTED")
    fill_allowed = campaign.base._allowed(
        state, fill_state_model, sparse_veto.FROZEN_ORIENTATION
    )
    opening = boundary.logical.clock.parent.parent._opening_by_late_stream[id(late)]
    gate = campaign.quality._fit(
        factors,
        late,
        late.active,
        campaign.FACTOR_SETS[definition["factor_set"]],
        float(definition["score_quantile"]),
        float(definition["ridge_alpha"]),
    )
    outer_score = campaign.quality._score(factors, gate)
    outer_allowed = np.isfinite(outer_score) & (outer_score >= gate["threshold"])
    expected = campaign.STREAM_TRANSFORM(late, outer_allowed)
    actual = assemble_forward_plan(
        opening_values=opening.values,
        opening_active=opening.active,
        anchor_values=anchor_values,
        anchor_active=anchor_active,
        fill_values=fill_values,
        fill_active=fill_active,
        fill_allowed=fill_allowed,
        outer_allowed=outer_allowed,
    )
    maximum_error = float(np.max(np.abs(expected.values - actual.values)))
    active_mismatches = int(np.count_nonzero(expected.active != actual.active))
    passed = maximum_error <= 1e-12 and active_mismatches == 0
    use_fill = (~anchor_active) & fill_active & fill_allowed
    # A transfer-route miss is knowable at bar 2.  Modern and fallback parent
    # misses are not knowable until their own bar-23 signal decisions.  Any
    # fill component entered before bar 24 on those sessions is retrospective.
    route_unresolved_until_bar23 = modern_state | ((~modern_state) & (~transfer_allowed))
    violating_components = []
    violating_session_mask = np.zeros(len(cube.sessions), dtype=bool)
    violating_contribution = np.zeros(len(cube.sessions))
    for parent_id, weight in zip(
        campaign.base.FILL_PARENTS, campaign.base.FILL_WEIGHTS, strict=True
    ):
        decision = int(models[parent_id].specification["decision"])
        entry = max(decision + 1, 11)
        if entry >= 24:
            continue
        violation = (
            route_unresolved_until_bar23 & use_fill & parents[parent_id][0].active
        )
        count = int(np.count_nonzero(violation))
        if count:
            violating_components.append(
                {
                    "parent_id": parent_id,
                    "decision_bar": decision,
                    "entry_bar": entry,
                    "violating_sessions": count,
                }
            )
            violating_session_mask |= violation
            violating_contribution += np.where(
                violation,
                float(weight) * parents[parent_id][0].values * actual.late_exposure,
                0.0,
            )
    violating_indices = np.flatnonzero(violating_session_mask)
    return {
        "schema_version": "1.0.0",
        "status": "COMPLETE" if passed else "FAILED",
        "candidate_id": CANDIDATE_ID,
        "sessions": len(cube.sessions),
        "maximum_absolute_daily_return_error": maximum_error,
        "active_session_mismatches": active_mismatches,
        "anchor_sessions": int(np.count_nonzero(actual.late_source == 1)),
        "fill_sessions": int(np.count_nonzero(actual.late_source == 2)),
        "cash_sessions": int(np.count_nonzero(actual.late_source == 0)),
        "full_exposure_sessions": int(np.count_nonzero(actual.late_exposure == 1.0)),
        "low_exposure_sessions": int(np.count_nonzero(actual.late_exposure == 0.25)),
        "daily_values_sha256": hashlib.sha256(
            np.asarray(actual.values, dtype="<f8").tobytes()
        ).hexdigest(),
        "passed": passed,
        "execution_causality": {
            "passed": len(violating_indices) == 0,
            "reason": (
                None
                if len(violating_indices) == 0
                else "FILL_ENTERED_BEFORE_BAR23_ROUTE_ABSENCE_WAS_KNOWABLE"
            ),
            "violating_sessions": len(violating_indices),
            "first_violating_session": (
                None if len(violating_indices) == 0 else str(cube.sessions[violating_indices[0]])
            ),
            "last_violating_session": (
                None if len(violating_indices) == 0 else str(cube.sessions[violating_indices[-1]])
            ),
            "violating_component_session_pairs": sum(
                item["violating_sessions"] for item in violating_components
            ),
            "affected_return_contribution_sum": float(violating_contribution.sum()),
            "affected_return_contribution_abs_sum": float(
                np.abs(violating_contribution).sum()
            ),
            "components": violating_components,
        },
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
