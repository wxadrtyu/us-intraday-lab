"""Freeze every fitted input needed to reproduce v10824 forward decisions.

This exporter is deliberately brokerless.  It turns the research-time model
graph into a plain JSON contract so a production evaluator never has to infer
or refit a parameter from later data.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
from pathlib import Path
from typing import Any

import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v39_multifactor_regime_gate as v39
import evaluate_full_universe_intraday_v5970_v6069_sector_flow_leadership as sector
import evaluate_full_universe_intraday_v10805_v10904_bar5_and_boundary as boundary
import numpy as np

CANDIDATE_ID = "lev-v10824-dc64eea19fd64bd8"
SELECTION_RANGE = [10805, 10904]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return _jsonable(dataclasses.asdict(value))
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def build_contract(root: Path, source_path: Path, selection_path: Path) -> dict[str, Any]:
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    if selection.get("status") != "COMPLETE" or selection.get("version_range") != SELECTION_RANGE:
        raise RuntimeError("V10824_SELECTION_NOT_FROZEN_COMPLETE")
    selected = [item for item in selection["records"] if item["candidate_id"] == CANDIDATE_ID]
    if len(selected) != 1 or not selected[0].get("strict_pre_factory_null_pass"):
        raise RuntimeError("V10824_FROZEN_CANDIDATE_CHANGED")

    boundary._configure()
    campaign = boundary.logical.clock.parent.parent.sparse_veto.campaign
    if campaign.base.prior.parent._sha(source_path) != campaign.base.prior.SOURCE_SHA256:
        raise RuntimeError("V10824_SOURCE_HASH_CHANGED")
    campaign.base.prior.cash._configure()
    source = json.loads(source_path.read_text(encoding="utf-8"))
    source_map = {item["candidate_id"]: item for item in source["records"]}
    base_ids = tuple(
        dict.fromkeys(
            (
                campaign.base.prior.route.MODERN_PARENT,
                campaign.base.prior.route.TRANSFER_PARENT,
                campaign.base.prior.cash.FALLBACK_PARENT,
            )
        )
    )
    required = tuple(dict.fromkeys((*base_ids, *campaign.base.FILL_PARENTS)))
    if any(item not in source_map for item in required):
        raise RuntimeError("V10824_FROZEN_PARENT_MISSING")

    development = v34.Cube(root, "alpaca", 0)
    factors = sector.SectorFlowLeadershipCube(root, "alpaca", 0)
    state = campaign.base.prior.parent.cross.Cube(root, "alpaca", 0)
    if not np.array_equal(development.dates, factors.dates):
        raise RuntimeError("V10824_FACTOR_DATE_AXIS_MISMATCH")
    parent_models = {
        item: v39._models(development, [source_map[item]["definition"]["strategy"]])[0]
        for item in required
    }
    parents = {
        item: campaign.base.prior.parent._parent_streams(
            development, source_map[item], parent_models[item]
        )
        for item in required
    }
    core_model = campaign.base.state._fit_state(
        state, campaign.base.CORE_LOW_DISPERSION_TREND, 0.20
    )
    override_model = campaign.base.state._fit_state(
        state, campaign.base.CORE_OVERSOLD_REPAIR, 0.35
    )
    _, transfer_state = campaign.base.prior.route._base_state(
        state, core_model, override_model
    )
    transfer_gate_model = campaign.base.prior.route._fit_gate(
        development,
        parents[campaign.base.prior.route.TRANSFER_PARENT][0],
        transfer_state,
        campaign.base.prior.route.FACTOR_SETS[campaign.base.prior.BASE_FAMILY],
        campaign.base.prior.BASE_QUANTILE,
        campaign.base.prior.BASE_ALPHA,
    )
    # The causal route ignores its legacy final argument and internally fits
    # this preregistered sparse-gap fill state.  Capture that exact model after
    # invoking the route instead of exporting the v6776 campaign placeholder.
    sparse_veto = boundary.logical.clock.parent.parent.sparse_veto
    fill_state_placeholder = campaign.base.state._fit_state(
        state, campaign.base.state.STATE_FAMILIES["high_vol_recovery"], 0.20
    )
    late = campaign._route(
        development,
        state,
        parents,
        core_model,
        override_model,
        transfer_gate_model,
        fill_state_placeholder,
    )[0]
    opening = boundary.logical.clock.parent.parent._opening_by_late_stream[id(late)]
    candidate = selected[0]["definition"]
    outer_gate_model = campaign.quality._fit(
        factors,
        late,
        late.active,
        campaign.FACTOR_SETS[candidate["factor_set"]],
        float(candidate["score_quantile"]),
        float(candidate["ridge_alpha"]),
    )
    opening_model = boundary.logical.clock.parent.parent.sparse_veto._opening_model
    fill_state_model = sparse_veto._fill_model
    if opening_model is None or fill_state_model is None:
        raise RuntimeError("V10824_ROUTE_MODEL_NOT_FITTED")

    contract: dict[str, Any] = {
        "schema_version": "1.0.0",
        "status": "FROZEN_FORWARD_INPUT_CONTRACT",
        "candidate_id": CANDIDATE_ID,
        "source_sha256": _sha(source_path),
        "selection_sha256": _sha(selection_path),
        "fit_contract": {
            "train": "2022-2023",
            "threshold_validation": "2024",
            "consumed_2026_used_for_fit_or_ranking": False,
        },
        "execution": {
            "long_only": True,
            "gross_limit": 1.0,
            "overnight": False,
            "bar_minutes": 5,
            "outer_gate_decision_bar": 5,
            "minimum_late_entry_bar": 11,
            "opening_decision_bar": 2,
            "opening_entry_bar": 3,
            "opening_exit_bar": 11,
            "outer_gate_low_exposure": boundary.logical.clock.parent.parent.LOW_EXPOSURE,
        },
        "symbols": list(v34.v12.SYMBOLS),
        "parents": {
            item: {
                "definition": source_map[item]["definition"],
                "fitted_signal_model": parent_models[item],
            }
            for item in required
        },
        "routing": {
            "modern_parent": campaign.base.prior.route.MODERN_PARENT,
            "transfer_parent": campaign.base.prior.route.TRANSFER_PARENT,
            "fallback_parent": campaign.base.prior.cash.FALLBACK_PARENT,
            "fill_parents": campaign.base.FILL_PARENTS,
            "fill_weights": campaign.base.FILL_WEIGHTS,
            "core_state_model": core_model,
            "override_state_model": override_model,
            "transfer_gate_model": transfer_gate_model,
            "fill_state_model": fill_state_model,
            "fill_state_family": sparse_veto.FROZEN_STATE_FAMILY,
            "fill_state_quantile": sparse_veto.FROZEN_STATE_QUANTILE,
            "fill_orientation": "fill_on_low",
        },
        "opening_model": opening_model,
        "outer_gate_model": outer_gate_model,
        "reference_stream_sha256": hashlib.sha256(
            np.asarray(opening.values + late.values, dtype="<f8").tobytes()
        ).hexdigest(),
    }
    encoded = _jsonable(contract)
    encoded["contract_sha256"] = hashlib.sha256(
        json.dumps(encoded, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return encoded


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    contract = build_contract(args.root, args.source, args.selection)
    v34.v12._atomic(args.output, contract)
    print(
        json.dumps(
            {
                "status": contract["status"],
                "candidate_id": contract["candidate_id"],
                "parent_count": len(contract["parents"]),
                "contract_sha256": contract["contract_sha256"],
            }
        )
    )


if __name__ == "__main__":
    main()
