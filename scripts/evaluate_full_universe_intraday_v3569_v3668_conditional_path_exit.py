"""Preregistered staged-recovery conditional-path-exit campaign."""

from __future__ import annotations

import evaluate_full_universe_intraday_v3469_v3568_staged_recovery as staged
import numpy as np

campaign = staged.campaign

POLICIES = {
    "flow_fixed": "fixed",
    "flow_fail_fast_loss": "fail_fast_loss",
    "flow_fail_fast_nonpositive": "fail_fast_nonpositive",
    "flow_profit_lock": "profit_lock",
    "flow_asymmetric": "asymmetric",
    "vwap_fail_fast_loss": "fail_fast_loss",
    "breadth_fail_fast_loss": "fail_fast_loss",
    "risk_fail_fast_loss": "fail_fast_loss",
    "flow_two_stage_retracement": "two_stage_retracement",
    "consensus_two_stage_retracement": "two_stage_retracement",
}


def _chosen_exit(
    policy: str,
    nominal_exit: int,
    first_exit: int,
    second_exit: int,
    first_return: np.ndarray,
    second_return: np.ndarray,
) -> np.ndarray:
    chosen = np.full(len(first_return), nominal_exit, dtype=int)
    if policy == "fixed":
        return chosen
    if policy == "fail_fast_loss":
        return np.where(first_return <= -0.003, first_exit, chosen)
    if policy == "fail_fast_nonpositive":
        return np.where(first_return <= 0.0, first_exit, chosen)
    if policy == "profit_lock":
        return np.where(first_return >= 0.006, first_exit, chosen)
    if policy == "asymmetric":
        return np.where((first_return <= -0.003) | (first_return >= 0.008), first_exit, chosen)
    if policy == "two_stage_retracement":
        first_stopped = first_return <= -0.003
        second_stopped = second_return <= first_return - 0.004
        chosen = np.where(second_stopped, second_exit, chosen)
        return np.where(first_stopped, first_exit, chosen)
    raise ValueError(f"UNKNOWN_EXIT_POLICY:{policy}")


def conditional_rule_raw(
    cube,
    definition: dict,
    mean: np.ndarray,
    scale: np.ndarray,
    threshold: float,
    cost: float,
    delay: int,
):
    decision = int(definition["decision"])
    nominal_exit = int(definition["exit"])
    factors = tuple(definition["factors"])
    directions = tuple(int(value) for value in definition["directions"])
    score = campaign.prior._rule_score(cube, decision, factors, directions, mean, scale)
    local = np.argmax(score, axis=1)
    selected = campaign.prior.ASSETS[local]
    best = score[cube.rows, local]
    active = np.isfinite(best) & (best >= threshold)
    if int(definition["confirmations"]) == 2:
        earlier = campaign.prior._rule_score(
            cube,
            decision - 3,
            factors,
            directions,
            mean,
            scale,
        )
        earlier_local = np.argmax(earlier, axis=1)
        earlier_best = earlier[cube.rows, earlier_local]
        active &= (
            (campaign.prior.ASSETS[earlier_local] == selected)
            & np.isfinite(earlier_best)
            & (earlier_best >= threshold)
        )

    entry = decision + 1 + delay
    first_checkpoint = decision + 6
    second_checkpoint = decision + 12
    first_exit = first_checkpoint + 1
    second_exit = second_checkpoint + 1
    policy = POLICIES[str(definition["mechanism"])]
    entry_price = cube.opens[cube.rows, entry, selected]
    first_return = cube.closes[cube.rows, first_checkpoint, selected] / entry_price - 1.0
    second_return = cube.closes[cube.rows, second_checkpoint, selected] / entry_price - 1.0
    chosen_exit = _chosen_exit(
        policy,
        nominal_exit,
        first_exit,
        second_exit,
        first_return,
        second_return,
    )

    active &= cube.first[cube.rows, entry, selected] <= entry * 5 + cube.boundary_tolerance
    active &= np.isfinite(entry_price) & (entry_price > 0)
    if policy != "fixed":
        active &= np.isfinite(first_return)
    if policy == "two_stage_retracement":
        active &= np.isfinite(second_return)
    exit_price = cube.opens[cube.rows, chosen_exit, selected]
    spy_entry = cube.opens[:, entry, 0]
    spy_exit = cube.opens[cube.rows, chosen_exit, 0]
    active &= (
        cube.first[cube.rows, chosen_exit, selected]
        <= chosen_exit * 5 + cube.boundary_tolerance
    )
    active &= np.isfinite(exit_price) & np.isfinite(spy_entry) & np.isfinite(spy_exit)
    active &= spy_entry > 0
    values = np.zeros(len(cube.sessions))
    values[active] = exit_price[active] / entry_price[active] - 1.0 - cost
    benchmark = np.zeros(len(cube.sessions))
    benchmark[active] = spy_exit[active] / spy_entry[active] - 1.0
    return campaign.prior.v12.ReturnStream(values, benchmark, active, active.astype(int))


def configure() -> None:
    campaign.FIRST_VERSION = 3569
    campaign.LAST_VERSION = 3668
    campaign.PRIOR_COMPARISON_CELLS = 176_105
    campaign.prior.v53.Cube = staged.StagedRecoveryCube
    campaign.prior._rule_raw = conditional_rule_raw
    campaign.HISTORICAL_MIN_ANNUALIZED_RETURN = 0.15
    campaign.REQUIRE_CONSUMED_2026Q1_GATE = True
    flow = (
        "prior3_return",
        "opening_stage_drawdown",
        "recovery_flow_imbalance",
        "volume_acceleration",
    )
    flow_directions = (-1, -1, 1, -1)
    campaign.FAMILIES = (
        ("flow_fixed", flow, flow_directions),
        ("flow_fail_fast_loss", flow, flow_directions),
        ("flow_fail_fast_nonpositive", flow, flow_directions),
        ("flow_profit_lock", flow, flow_directions),
        ("flow_asymmetric", flow, flow_directions),
        (
            "vwap_fail_fast_loss",
            ("prior5_return", "vwap_reclaim_slope", "recovery_efficiency", "signed_volume_imbalance"),
            (-1, 1, 1, 1),
        ),
        (
            "breadth_fail_fast_loss",
            ("prior3_return", "recovery_stage_return", "sector_breadth_repair", "risk_agreement_repair"),
            (-1, 1, 1, 1),
        ),
        (
            "risk_fail_fast_loss",
            ("prior5_downside_volatility", "recovery_stage_return", "risk_agreement_repair", "sector_breadth_repair"),
            (1, 1, 1, 1),
        ),
        ("flow_two_stage_retracement", flow, flow_directions),
        (
            "consensus_two_stage_retracement",
            ("prior3_return", "opening_stage_drawdown", "recovery_stage_return", "recovery_efficiency", "recovery_flow_imbalance"),
            (-1, -1, 1, 1, 1),
        ),
    )
    campaign.SCHEDULES = ((23, 47), (23, 50), (23, 53), (23, 56), (23, 59))
    campaign.STATE_MODES = ("unfiltered", "orderly_rebound_cash_filter")


if __name__ == "__main__":
    configure()
    campaign.main()
