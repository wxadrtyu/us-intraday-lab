"""Prior-day full-session risk gate over the parity-proven branch architecture."""

from __future__ import annotations

import evaluate_full_universe_intraday_v11708_v11807_branch_causal_hard_veto as hard
import numpy as np

FIRST_VERSION = 11909
LAST_VERSION = 12008
PRIOR_COMPARISON_CELLS = 312_083
QUANTILES = (0.10, 0.25, 0.50, 0.75, 0.90)
ALPHAS = (0.0,)
STATE_FAMILIES = (
    "defensive_leadership",
    "quiet_growth_repair",
    "broad_oversold_stability",
    "smallcap_growth_divergence",
    "cyclical_low_vol",
    "volatile_breadth_repair",
    "tech_without_concentration",
    "smallcap_confirmation_low_vol",
    "risk_agreement_repair",
    "balanced_defensive_growth",
)
GATE_SPECS = {
    f"{family}_{orientation}": (family, orientation)
    for family in STATE_FAMILIES
    for orientation in ("high", "low")
}
FACTOR_SETS = {name: (name,) for name in GATE_SPECS}


def _fit_prior_gate(cube, _stream, _active, factors, quantile, _alpha):
    name = factors[0]
    family, orientation = GATE_SPECS[name]
    state = hard.branch.boundary.logical.clock.parent.parent.sparse_veto.campaign.base.state
    fitted = state._fit_state(cube, state.STATE_FAMILIES[family], quantile)
    return {
        "prior_day_full_session_gate": True,
        "name": name,
        "orientation": orientation,
        "state_model": fitted,
        "factors": (name,),
        "mean": np.asarray([0.0]),
        "scale": np.asarray([1.0]),
        "coefficients": np.asarray([1.0]),
        "threshold": 0.0,
    }


def _score_prior_gate(cube, model):
    state = hard.branch.boundary.logical.clock.parent.parent.sparse_veto.campaign.base.state
    raw = state._score(cube, model["state_model"])
    finite = np.isfinite(raw)
    if model["orientation"] == "high":
        allowed = finite & (raw >= model["state_model"]["threshold"])
    else:
        allowed = finite & (raw < model["state_model"]["threshold"])
    return np.where(allowed, 1.0, -1.0)


def _full_session_cash_gate(stream, allowed):
    opening_parent = hard.branch.boundary.logical.clock.parent.parent
    opening = opening_parent._opening_by_late_stream.get(id(stream))
    if opening is None:
        raise RuntimeError("PRIOR_DAY_GATE_OPENING_STREAM_NOT_REGISTERED")
    active = (stream.active | opening.active) & allowed
    return hard.branch.repriced.v34.v12.ReturnStream(
        np.where(allowed, stream.values + opening.values, 0.0),
        np.where(allowed, stream.benchmark + opening.benchmark, 0.0),
        active,
        np.where(allowed, stream.component_trades + opening.component_trades, 0),
    )


def _configure() -> None:
    hard._configure()
    campaign = hard.branch.boundary.logical.clock.parent.parent.sparse_veto.campaign
    campaign.FIRST_VERSION = FIRST_VERSION
    campaign.LAST_VERSION = LAST_VERSION
    campaign.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    campaign.EFFECTIVE_FIRST_VERSION = LAST_VERSION + 1
    campaign.FACTOR_SETS = FACTOR_SETS
    campaign.QUANTILES = QUANTILES
    campaign.ALPHAS = ALPHAS
    campaign.quality._fit = _fit_prior_gate
    campaign.quality._score = _score_prior_gate
    campaign.STREAM_TRANSFORM = _full_session_cash_gate
    campaign.MECHANISM = "prior_day_state_full_session_cash_gate"


if __name__ == "__main__":
    _configure()
    hard.branch.boundary.logical.clock.parent.parent.sparse_veto.campaign.main()
