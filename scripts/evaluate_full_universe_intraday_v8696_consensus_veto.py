"""v8696: majority consensus across sparse-gap loss-veto families."""

from __future__ import annotations

import hashlib
import json
import math

import evaluate_full_universe_intraday_v7595_loss_veto_ensemble as ensemble
import evaluate_full_universe_intraday_v8396_v8495_sparse_gap_loss_veto as sparse_veto
import numpy as np

VERSION = 8696
PRIOR_COMPARISON_CELLS = 257_566
SELECTION_VERSION_RANGE = [8396, 8495]
CONSENSUS_SHARE = 0.60


def _consensus(streams):
    count = sum((stream.active.astype(int) for stream in streams), np.zeros(len(streams[0].active), dtype=int))
    required = math.ceil(CONSENSUS_SHARE * len(streams))
    active = count >= required
    denominator = np.maximum(count, 1)
    values = sum((stream.values for stream in streams), np.zeros(len(active))) / denominator
    benchmark = sum((stream.benchmark for stream in streams), np.zeros(len(active))) / denominator
    component_trades = np.maximum.reduce([stream.component_trades for stream in streams])
    return ensemble.v34.v12.ReturnStream(
        np.where(active, values, 0.0),
        np.where(active, benchmark, 0.0),
        active,
        np.where(active, component_trades, 0),
    )


def _compound(values):
    return float(np.prod(1.0 + values) - 1.0)


def _consensus_native_null(route, allowed, variants, development_mask):
    index = np.flatnonzero(development_mask)
    route_values = route.values[index]
    selected = [mask[index] for mask in allowed]

    def profit(masks, variant):
        votes = sum((masks[item].astype(int) for item in variant), np.zeros(len(index), dtype=int))
        accepted = votes >= math.ceil(CONSENSUS_SHARE * len(variant))
        return _compound(np.where(accepted, route_values, 0.0))

    observed = profit(selected, variants[0])
    rng = np.random.default_rng(ensemble.NULL_SEED)
    permutation_max = []
    shift_max = []
    for _ in range(ensemble.NULL_REPETITIONS):
        permuted = [mask[rng.permutation(len(index))] for mask in selected]
        shifts = [
            np.roll(mask, int(rng.integers(ensemble.SAFE_SHIFT_MINIMUM, len(index) - 4)))
            for mask in selected
        ]
        permutation_max.append(max(profit(permuted, variant) for variant in variants))
        shift_max.append(max(profit(shifts, variant) for variant in variants))
    evidence = {
        "observed_profit": observed,
        "permutation_maxT_95pct": float(np.quantile(permutation_max, ensemble.NULL_PERCENTILE)),
        "safe_shift_maxT_95pct": float(np.quantile(shift_max, ensemble.NULL_PERCENTILE)),
        "seed": ensemble.NULL_SEED,
        "repetitions": ensemble.NULL_REPETITIONS,
        "percentile": ensemble.NULL_PERCENTILE,
        "consensus_share": CONSENSUS_SHARE,
    }
    evidence["passed"] = (
        observed > evidence["permutation_maxT_95pct"]
        and observed > evidence["safe_shift_maxT_95pct"]
    )
    evidence["evidence_sha256"] = hashlib.sha256(
        json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return evidence


def _configure():
    sparse_veto._configure()
    ensemble.VERSION = VERSION
    ensemble.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    ensemble.SELECTION_VERSION_RANGE = SELECTION_VERSION_RANGE
    ensemble.COMPONENT_COMBINER = _consensus
    ensemble.NATIVE_NULL = _consensus_native_null
    ensemble.MECHANISM = "majority_consensus_sparse_gap_loss_veto_ensemble"
    ensemble.COMPONENT_WEIGHT = None


if __name__ == "__main__":
    _configure()
    ensemble.main()
