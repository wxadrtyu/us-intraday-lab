"""Evaluate 2021-2023-frozen symbol and calendar intraday return priors."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from runpy import run_path

import pandas as pd

BASE = run_path(
    str(Path(__file__).with_name("evaluate_us_market_v14809_v14908_normalized_events.py")),
    run_name="v14809_common",
)
FAMILIES = (
    "symbol_bar_prior",
    "weekday_prior",
    "month_prior",
    "week_of_month_prior",
    "quarter_prior",
)
GROUPS = {
    FAMILIES[0]: ([], 100, 0.0010),
    FAMILIES[1]: (["weekday"], 20, 0.0012),
    FAMILIES[2]: (["calendar_month"], 20, 0.0012),
    FAMILIES[3]: (["week_of_month"], 20, 0.0015),
    FAMILIES[4]: (["quarter"], 60, 0.0010),
}


def attach_calendar_priors(events: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int | str]]:
    frame = events.copy()
    frame["weekday"] = frame["session_date"].dt.weekday
    frame["calendar_month"] = frame["session_date"].dt.month
    frame["week_of_month"] = ((frame["session_date"].dt.day - 1) // 7 + 1).clip(upper=5)
    frame["quarter"] = frame["session_date"].dt.quarter
    frame["training_next_5m_return"] = frame["p2_open"] / frame["p1_open"] - 1.0
    training = frame.loc[
        (frame["session_date"] >= "2021-01-01")
        & (frame["session_date"] <= "2023-12-31")
    ].copy()
    evidence: dict[str, int | str] = {"method": "2021-2023 frozen next-5m means"}
    for family, (calendar_columns, minimum_count, _) in GROUPS.items():
        keys = ["symbol", "bar_idx", *calendar_columns]
        priors = training.groupby(keys, as_index=False).agg(
            prior_observations=("training_next_5m_return", "count"),
            expected_return=("training_next_5m_return", "mean"),
        )
        priors = priors.loc[priors["prior_observations"] >= minimum_count]
        priors = priors.rename(
            columns={
                "prior_observations": f"{family}_observations",
                "expected_return": f"{family}_expected_return",
            }
        )
        frame = frame.merge(priors, on=keys, how="left", validate="many_to_one")
        evidence[f"{family}_cells"] = len(priors)
    evidence["attached_events"] = len(frame)
    return frame, evidence


def event_mask(frame: pd.DataFrame, family: str) -> pd.Series:
    floor = GROUPS[family][2]
    return frame[f"{family}_expected_return"] > floor


def score(frame: pd.DataFrame, family: str) -> pd.Series:
    return frame[f"{family}_expected_return"]


def format_metric(value: float | None, specifier: str) -> str:
    return "NA" if value is None else format(value, specifier)


def run(args: argparse.Namespace) -> dict:
    evaluator_globals = BASE["run"].__globals__
    evaluator_globals.update(
        {
            "FAMILIES": FAMILIES,
            "FIRST_VERSION": 16809,
            "PRIOR_COMPARISONS": 339_683,
            "TOP_COUNT_BY_DECISION": None,
            "attach_training_scales": attach_calendar_priors,
            "event_mask": event_mask,
            "score": score,
        }
    )
    result = BASE["run"](args)
    result["campaign_id"] = "v16809-v16908-frozen-calendar-return-priors"
    result["calendar_prior_evidence"] = result.pop("training_only_scale_evidence")
    BASE["COMMON"]["atomic_json"](Path(args.output), result)
    best = result["results_by_development_rank"][0]
    Path(args.output).with_suffix(".md").write_text(
        "# v16809-v16908 frozen calendar return priors\n\n"
        f"- Status: COMPLETE; versions: {result['versions_completed']}; admitted: 0\n"
        f"- Best: v{best['version']} ({best['family']}, bar {best['decision_bar']}, hold {best['holding_minutes']}m)\n"
        + "\n".join(
            f"- {name}: annualized {format_metric(value['annualized_return'], '.2%')}, "
            f"MDD {format_metric(value['max_drawdown'], '.2%')}, "
            f"IR {format_metric(value['information_ratio'], '.2f')}"
            for name, value in best["development_oos"].items()
        )
        + f"\n- 2026Q1 consumed 9bp total: {best['consumed_2026q1']['standard_9bp']['total_return']:.2%}\n"
        "- Final admission: NO; all hard gates and historical supplement remain mandatory.\n",
        encoding="utf-8",
    )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default=r"E:\us-intraday-lab-data\us-market")
    parser.add_argument("--output", default="research/results/2026-09-07-v16809-v16908-calendar-priors.json")
    return parser.parse_args()


if __name__ == "__main__":
    summary = run(parse_args())
    print(json.dumps({key: summary[key] for key in ("status", "versions_completed", "pre_null_candidates", "admitted_candidates", "elapsed_seconds")}, indent=2))
