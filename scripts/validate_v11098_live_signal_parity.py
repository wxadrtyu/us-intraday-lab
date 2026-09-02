"""Replay the frozen v11098 live leg adapter against the research stream."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import evaluate_full_universe_intraday_v35_rank_ensemble as v35
import evaluate_full_universe_intraday_v5970_v6069_sector_flow_leadership as sector
import evaluate_full_universe_intraday_v11006_v11105_branch_causal as branch
import numpy as np
import validate_v10905_causal_bar5_and_native_null as native
from v11098_live_frame_adapter import (
    _daily_gate_score,
    _parent_exposure,
    _parent_signal,
    _prior_state_score,
    load_contract,
    signals_for_session,
)

CANDIDATE_ID = "lev-v11098-2ddc1d07c9cfe31e"
CAMPAIGN_CONFIGURE = branch._configure


class _Facade:
    logical = branch.boundary.logical

    @staticmethod
    def _configure() -> None:
        CAMPAIGN_CONFIGURE()


def validate(root: Path, source: Path, selection_path: Path, contract_path: Path) -> dict:
    native.boundary = _Facade
    campaign, _development, factors, late, opening = native._development_route(root, source)
    sparse_veto = branch.boundary.logical.clock.parent.parent.sparse_veto
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    candidate = next(
        item
        for item in selection["records"]
        if item["candidate_id"] == CANDIDATE_ID
    )
    definition = candidate["definition"]
    model = campaign.quality._fit(
        factors,
        late,
        late.active,
        campaign.FACTOR_SETS[definition["factor_set"]],
        float(definition["score_quantile"]),
        float(definition["ridge_alpha"]),
    )
    score = campaign.quality._score(factors, model)
    outer = np.where(
        np.isfinite(score) & (score >= model["threshold"]),
        1.0,
        branch.boundary.logical.clock.parent.parent.LOW_EXPOSURE,
    )
    expected = opening.values + late.values * outer
    expected_active = opening.active | late.active

    cube = sector.SectorFlowLeadershipCube(root, "alpaca", 0)
    cube._v11098_parent_cube = _development
    parent_cube = _development
    contract = load_contract(contract_path, CANDIDATE_ID)
    frozen_outer = contract["outer_gate_model"]
    frozen_left = _daily_gate_score(cube, frozen_outer["left"], 5)
    frozen_right = _daily_gate_score(cube, frozen_outer["right"], 5)
    frozen_allowed = (
        np.isfinite(frozen_left)
        & (frozen_left >= frozen_outer["left"]["threshold"])
        & np.isfinite(frozen_right)
        & (frozen_right >= frozen_outer["right"]["threshold"])
    )
    direct_allowed = np.isfinite(score) & (score >= model["threshold"])
    outer_gate_mismatches = int(np.count_nonzero(frozen_allowed != direct_allowed))
    routing = contract["routing"]
    state_cube = campaign.base.prior.parent.cross.Cube(root, "alpaca", 0)
    direct_core_model = campaign.base.state._fit_state(
        state_cube, campaign.base.CORE_LOW_DISPERSION_TREND, 0.20
    )
    direct_override_model = campaign.base.state._fit_state(
        state_cube, campaign.base.CORE_OVERSOLD_REPAIR, 0.35
    )
    direct_modern, _direct_transfer_state = campaign.base.prior.route._base_state(
        state_cube, direct_core_model, direct_override_model
    )
    frozen_core = _prior_state_score(cube, routing["core_state_model"])
    frozen_override = _prior_state_score(cube, routing["override_state_model"])
    frozen_core_high = np.isfinite(frozen_core) & (
        frozen_core >= routing["core_state_model"]["threshold"]
    )
    frozen_override_low = np.isfinite(frozen_override) & (
        frozen_override < routing["override_state_model"]["threshold"]
    )
    frozen_modern = frozen_core_high | ((~frozen_core_high) & frozen_override_low)
    modern_state_mismatches = int(np.count_nonzero(frozen_modern != direct_modern))
    parent_checks = []
    reference_parents = {}
    reference_late_parents = {}
    for parent_id, parent in contract["parents"].items():
        encoded = parent["fitted_signal_model"]
        rank_model = v35.RankModel(
            specification=encoded["specification"],
            factors=tuple(encoded["factors"]),
            mean=np.asarray(encoded["mean"]),
            scale=np.asarray(encoded["scale"]),
            direction=np.asarray(encoded["direction"]),
            weights=np.asarray(encoded["weights"]),
            threshold=float(encoded["threshold"]),
            diagnostics=encoded["diagnostics"],
        )
        reference_parent = branch._scaled_scenarios(
            parent_cube, parent, rank_model, branch.EARLY_MINIMUM_ENTRY_BAR
        )[0]
        reference_parents[parent_id] = reference_parent
        selected, active = _parent_signal(parent_cube, parent)
        exposure = _parent_exposure(parent_cube, parent, branch.EARLY_MINIMUM_ENTRY_BAR)
        decision = int(encoded["specification"]["decision"])
        entry = max(decision + 1, branch.EARLY_MINIMUM_ENTRY_BAR)
        exit_bar = int(encoded["specification"]["exit"])
        realized = np.zeros(len(cube.sessions))
        quality = active.copy()
        quality &= parent_cube.first[parent_cube.rows, entry, selected] <= entry * 5
        quality &= parent_cube.first[parent_cube.rows, exit_bar, selected] <= exit_bar * 5
        quality &= np.isfinite(parent_cube.opens[parent_cube.rows, entry, selected])
        quality &= np.isfinite(parent_cube.opens[parent_cube.rows, exit_bar, selected])
        quality &= np.isfinite(parent_cube.opens[:, entry, 0])
        quality &= np.isfinite(parent_cube.opens[:, exit_bar, 0])
        realized[quality] = exposure[quality] * (
            parent_cube.opens[parent_cube.rows[quality], exit_bar, selected[quality]]
            / parent_cube.opens[parent_cube.rows[quality], entry, selected[quality]]
            - 1.0
            - 0.0009
        )
        parent_checks.append(
            {
                "parent_id": parent_id,
                "maximum_error": float(np.max(np.abs(reference_parent.values - realized))),
                "active_mismatches": int(
                    np.count_nonzero(reference_parent.active != (quality & (exposure > 0)))
                ),
            }
        )
        reference_late = branch._scaled_scenarios(
            parent_cube, parent, rank_model, branch.LATE_MINIMUM_ENTRY_BAR
        )[0]
        reference_late_parents[parent_id] = reference_late
        late_exposure = _parent_exposure(parent_cube, parent, branch.LATE_MINIMUM_ENTRY_BAR)
        late_entry = max(decision + 1, branch.LATE_MINIMUM_ENTRY_BAR)
        late_quality = active.copy()
        late_quality &= parent_cube.first[parent_cube.rows, late_entry, selected] <= late_entry * 5
        late_quality &= parent_cube.first[parent_cube.rows, exit_bar, selected] <= exit_bar * 5
        late_quality &= np.isfinite(parent_cube.opens[parent_cube.rows, late_entry, selected])
        late_quality &= np.isfinite(parent_cube.opens[parent_cube.rows, exit_bar, selected])
        late_quality &= np.isfinite(parent_cube.opens[:, late_entry, 0])
        late_quality &= np.isfinite(parent_cube.opens[:, exit_bar, 0])
        late_realized = np.zeros(len(cube.sessions))
        late_realized[late_quality] = late_exposure[late_quality] * (
            parent_cube.opens[parent_cube.rows[late_quality], exit_bar, selected[late_quality]]
            / parent_cube.opens[parent_cube.rows[late_quality], late_entry, selected[late_quality]]
            - 1.0
            - 0.0009
        )
        parent_checks.append(
            {
                "parent_id": parent_id + ":late",
                "maximum_error": float(np.max(np.abs(reference_late.values - late_realized))),
                "active_mismatches": int(
                    np.count_nonzero(reference_late.active != (late_quality & (late_exposure > 0)))
                ),
            }
        )
    direct_transfer_gate = campaign.base.prior.route._fit_gate(
        cube,
        reference_parents[routing["transfer_parent"]],
        _direct_transfer_state,
        campaign.base.prior.route.FACTOR_SETS[campaign.base.prior.BASE_FAMILY],
        campaign.base.prior.BASE_QUANTILE,
        campaign.base.prior.BASE_ALPHA,
    )
    direct_transfer_score = campaign.base.prior.route._score(parent_cube, direct_transfer_gate)
    frozen_transfer_score = _daily_gate_score(parent_cube, routing["transfer_gate_model"], 2)
    direct_transfer_allowed = np.isfinite(direct_transfer_score) & (
        direct_transfer_score >= direct_transfer_gate["threshold"]
    )
    frozen_transfer_allowed = np.isfinite(frozen_transfer_score) & (
        frozen_transfer_score >= routing["transfer_gate_model"]["threshold"]
    )
    transfer_gate_mismatches = int(
        np.count_nonzero(direct_transfer_allowed != frozen_transfer_allowed)
    )
    direct_fill_model = campaign.base.state._fit_state(
        state_cube,
        campaign.base.state.STATE_FAMILIES[sparse_veto.FROZEN_STATE_FAMILY],
        sparse_veto.FROZEN_STATE_QUANTILE,
    )
    direct_fill_score = campaign.base.state._score(state_cube, direct_fill_model)
    frozen_fill_score = _prior_state_score(cube, routing["fill_state_model"])
    direct_fill_allowed = np.isfinite(direct_fill_score) & (
        direct_fill_score < direct_fill_model["threshold"]
    )
    frozen_fill_allowed = np.isfinite(frozen_fill_score) & (
        frozen_fill_score < routing["fill_state_model"]["threshold"]
    )
    fill_gate_mismatches = int(np.count_nonzero(direct_fill_allowed != frozen_fill_allowed))
    frozen_transfer_branch = (~frozen_modern) & frozen_transfer_allowed
    frozen_anchor_values = np.where(
        frozen_modern,
        reference_late_parents[routing["modern_parent"]].values,
        np.where(
            frozen_transfer_branch,
            reference_parents[routing["transfer_parent"]].values,
            reference_late_parents[routing["fallback_parent"]].values,
        ),
    )
    frozen_anchor_active = np.where(
        frozen_modern,
        reference_late_parents[routing["modern_parent"]].active,
        np.where(
            frozen_transfer_branch,
            reference_parents[routing["transfer_parent"]].active,
            reference_late_parents[routing["fallback_parent"]].active,
        ),
    )
    frozen_fill_values = np.zeros(len(cube.sessions))
    frozen_fill_active = np.zeros(len(cube.sessions), dtype=bool)
    for fill_id, weight in zip(routing["fill_parents"], routing["fill_weights"], strict=True):
        early_stream = reference_parents[fill_id]
        late_stream = reference_late_parents[fill_id]
        frozen_fill_values += float(weight) * np.where(
            frozen_transfer_branch, early_stream.values, late_stream.values
        )
        frozen_fill_active |= np.where(
            frozen_transfer_branch, early_stream.active, late_stream.active
        )
    frozen_use_fill = (~frozen_anchor_active) & frozen_fill_active & frozen_fill_allowed
    frozen_route_values = np.where(
        frozen_anchor_active,
        frozen_anchor_values,
        np.where(frozen_use_fill, frozen_fill_values, 0.0),
    )
    frozen_route_active = frozen_anchor_active | frozen_use_fill
    frozen_route_reference_error = float(np.max(np.abs(late.values - frozen_route_values)))
    frozen_route_reference_active_mismatches = int(
        np.count_nonzero(late.active != frozen_route_active)
    )
    direct_transfer_branch = (~direct_modern) & direct_transfer_allowed
    direct_anchor_values = np.where(
        direct_modern,
        reference_late_parents[routing["modern_parent"]].values,
        np.where(
            direct_transfer_branch,
            reference_parents[routing["transfer_parent"]].values,
            reference_late_parents[routing["fallback_parent"]].values,
        ),
    )
    direct_anchor_active = np.where(
        direct_modern,
        reference_late_parents[routing["modern_parent"]].active,
        np.where(
            direct_transfer_branch,
            reference_parents[routing["transfer_parent"]].active,
            reference_late_parents[routing["fallback_parent"]].active,
        ),
    )
    direct_fill_values = np.zeros(len(cube.sessions))
    direct_fill_active = np.zeros(len(cube.sessions), dtype=bool)
    for fill_id, weight in zip(routing["fill_parents"], routing["fill_weights"], strict=True):
        early_stream = reference_parents[fill_id]
        late_stream = reference_late_parents[fill_id]
        direct_fill_values += float(weight) * np.where(
            direct_transfer_branch, early_stream.values, late_stream.values
        )
        direct_fill_active |= np.where(
            direct_transfer_branch, early_stream.active, late_stream.active
        )
    direct_use_fill = (~direct_anchor_active) & direct_fill_active & direct_fill_allowed
    direct_route_values = np.where(
        direct_anchor_active,
        direct_anchor_values,
        np.where(direct_use_fill, direct_fill_values, 0.0),
    )
    direct_route_active = direct_anchor_active | direct_use_fill
    direct_route_reference_error = float(np.max(np.abs(late.values - direct_route_values)))
    direct_route_reference_active_mismatches = int(
        np.count_nonzero(late.active != direct_route_active)
    )
    actual = np.zeros(len(cube.sessions))
    actual_opening = np.zeros(len(cube.sessions))
    actual_active = np.zeros(len(cube.sessions), dtype=bool)
    leg_count = 0
    gross_violation = 0
    for index in range(60, len(cube.sessions)):
        legs = signals_for_session(
            cube,
            contract,
            cube.dates[index].date(),
            require_realized_quality=True,
        )
        leg_count += len(legs)
        by_bar = {}
        for leg in legs:
            by_bar[leg.entry_bar] = by_bar.get(leg.entry_bar, 0.0) + leg.weight * leg.exposure
            selected = list(contract["symbols"]).index(leg.symbol)
            valid = (
                cube.first[index, leg.entry_bar, selected] <= leg.entry_bar * 5
                and cube.first[index, leg.exit_bar, selected] <= leg.exit_bar * 5
                and np.isfinite(cube.opens[index, leg.entry_bar, selected])
                and np.isfinite(cube.opens[index, leg.exit_bar, selected])
            )
            if not valid:
                continue
            contribution = (
                leg.weight
                * leg.exposure
                * (
                    cube.opens[index, leg.exit_bar, selected]
                    / cube.opens[index, leg.entry_bar, selected]
                    - 1.0
                    - 0.0009
                )
            )
            actual[index] += contribution
            if leg.sleeve == "opening":
                actual_opening[index] += contribution
            actual_active[index] = True
        # Opening and late entries can share bar 11 only as an exit/entry handoff.
        gross_violation += int(any(value > 1.0 + 1e-12 for value in by_bar.values()))
    compared = np.arange(60, len(cube.sessions))
    error = float(np.max(np.abs(expected[compared] - actual[compared])))
    opening_error = float(np.max(np.abs(opening.values[compared] - actual_opening[compared])))
    late_error = float(
        np.max(
            np.abs(
                late.values[compared] * outer[compared]
                - (actual[compared] - actual_opening[compared])
            )
        )
    )
    active_mismatches = int(np.count_nonzero(expected_active[compared] != actual_active[compared]))
    passed = error <= 1e-12 and active_mismatches == 0 and gross_violation == 0
    difference = np.abs(expected - actual)
    mismatch_indices = compared[
        (difference[compared] > 1e-12) | (expected_active[compared] != actual_active[compared])
    ]
    return {
        "schema_version": "1.0.0",
        "status": "COMPLETE" if passed else "FAILED",
        "candidate_id": contract["candidate_id"],
        "compared_sessions": len(compared),
        "emitted_legs": leg_count,
        "maximum_absolute_daily_return_error": error,
        "maximum_opening_error": opening_error,
        "maximum_late_route_error": late_error,
        "active_session_mismatches": active_mismatches,
        "gross_limit_violations": gross_violation,
        "outer_gate_mismatches": outer_gate_mismatches,
        "modern_state_mismatches": modern_state_mismatches,
        "transfer_gate_mismatches": transfer_gate_mismatches,
        "fill_gate_mismatches": fill_gate_mismatches,
        "frozen_route_reference_error": frozen_route_reference_error,
        "frozen_route_reference_active_mismatches": frozen_route_reference_active_mismatches,
        "direct_route_reference_error": direct_route_reference_error,
        "direct_route_reference_active_mismatches": direct_route_reference_active_mismatches,
        "parent_checks_failed": [
            item
            for item in parent_checks
            if item["maximum_error"] > 1e-12 or item["active_mismatches"]
        ],
        "mismatch_sessions": len(mismatch_indices),
        "last_mismatch_session": (
            None if len(mismatch_indices) == 0 else str(cube.sessions[mismatch_indices[-1]])
        ),
        "mismatch_examples": [
            {
                "session": str(cube.sessions[index]),
                "expected": float(expected[index]),
                "actual": float(actual[index]),
                "expected_active": bool(expected_active[index]),
                "actual_active": bool(actual_active[index]),
            }
            for index in mismatch_indices[:20]
        ],
        "passed": passed,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = validate(args.root, args.source, args.selection, args.contract)
    native.v34.v12._atomic(args.output, result)
    print(json.dumps(result))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
