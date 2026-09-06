"""Evaluate a 2021-2023-frozen stock-to-stock intraday leader network."""

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
    "top1_leader_impulse",
    "top3_leader_consensus",
    "top5_leader_consensus",
    "concentrated_leader_impulse",
    "volume_confirmed_network",
)
EXCLUDED_LEADERS = {"SPY", "QQQ", "IWM"}


def estimate_mapping(training: pd.DataFrame) -> tuple[pd.DataFrame, int, list[str]]:
    liquid = (
        training.loc[~training["symbol"].isin(EXCLUDED_LEADERS)]
        .groupby("symbol")["volume"]
        .median()
        .sort_values(ascending=False)
    )
    leaders = liquid.head(50).index.tolist()
    records: list[dict[str, int | float | str]] = []
    comparisons = 0
    for bar_idx in (2, 5, 11, 17, 23):
        subset = training.loc[training["bar_idx"] == bar_idx]
        leader_returns = subset.loc[subset["symbol"].isin(leaders)].pivot(
            index="session_date", columns="symbol", values="ret1"
        )
        target_returns = subset.pivot(
            index="session_date", columns="symbol", values="network_target_return"
        )
        for target in target_returns.columns:
            target_series = target_returns[target]
            correlations = leader_returns.corrwith(target_series)
            observations = leader_returns.notna().mul(target_series.notna(), axis=0).sum()
            comparisons += len(correlations)
            eligible = pd.DataFrame(
                {"leader_symbol": correlations.index, "correlation": correlations.values,
                 "observations": observations.reindex(correlations.index).values}
            )
            eligible = eligible.loc[
                (eligible["leader_symbol"] != target)
                & (eligible["observations"] >= 100)
                & (eligible["correlation"] > 0.08)
            ].nlargest(5, "correlation")
            if len(eligible) < 5:
                continue
            for rank, row in enumerate(eligible.itertuples(index=False), start=1):
                records.append(
                    {"target_symbol": target, "bar_idx": bar_idx,
                     "leader_symbol": row.leader_symbol, "leader_rank": rank,
                     "correlation": float(row.correlation),
                     "observations": int(row.observations)}
                )
    return pd.DataFrame(records), comparisons, leaders


def aggregate_prediction(long: pd.DataFrame, count: int) -> pd.DataFrame:
    subset = long.loc[long["leader_rank"] <= count].copy()
    subset["weighted_signal"] = subset["correlation"] * subset["leader_ret1"]
    subset["positive_leader"] = (subset["leader_ret1"] > 0.0).astype(float)
    keys = ["target_symbol", "session_date", "bar_idx"]
    aggregate = subset.groupby(keys, as_index=False).agg(
        available_leaders=("leader_symbol", "size"),
        weighted_signal=("weighted_signal", "sum"),
        correlation_sum=("correlation", "sum"),
        positive_share=("positive_leader", "mean"),
        mean_leader_volume_rank=("leader_volume_rank", "mean"),
        largest_correlation=("correlation", "max"),
    )
    aggregate = aggregate.loc[aggregate["available_leaders"] == count]
    aggregate[f"prediction_top{count}"] = aggregate["weighted_signal"] / aggregate["correlation_sum"]
    aggregate[f"positive_share_top{count}"] = aggregate["positive_share"]
    aggregate[f"mean_volume_rank_top{count}"] = aggregate["mean_leader_volume_rank"]
    aggregate[f"concentration_top{count}"] = aggregate["largest_correlation"] / aggregate["correlation_sum"]
    return aggregate[[
        *keys, f"prediction_top{count}", f"positive_share_top{count}",
        f"mean_volume_rank_top{count}", f"concentration_top{count}",
    ]]


def attach_leader_network(events: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int | str]]:
    frame = events.copy()
    frame["network_target_return"] = frame["p2_open"] / frame["p1_open"] - 1.0
    training = frame.loc[
        (frame["session_date"] >= "2021-01-01")
        & (frame["session_date"] <= "2023-12-31")
    ]
    mapping, comparisons, leaders = estimate_mapping(training)
    if mapping.empty:
        raise RuntimeError("frozen leader mapping is empty")
    targets = frame[["symbol", "session_date", "bar_idx"]].rename(columns={"symbol": "target_symbol"})
    long = targets.merge(mapping, on=["target_symbol", "bar_idx"], how="inner", validate="many_to_many")
    leader_values = frame[["symbol", "session_date", "bar_idx", "ret1", "volume_rank"]].rename(
        columns={"symbol": "leader_symbol", "ret1": "leader_ret1",
                 "volume_rank": "leader_volume_rank"}
    )
    long = long.merge(
        leader_values, on=["leader_symbol", "session_date", "bar_idx"],
        how="inner", validate="many_to_one"
    )
    attached = frame
    for count in (1, 3, 5):
        prediction = aggregate_prediction(long, count)
        prediction = prediction.rename(columns={"target_symbol": "symbol"})
        attached = attached.merge(
            prediction, on=["symbol", "session_date", "bar_idx"],
            how="left", validate="one_to_one"
        )
    return attached, {
        "attached_events": len(attached), "leader_symbols": len(leaders),
        "mapping_rows": len(mapping), "mapping_targets": mapping["target_symbol"].nunique(),
        "mapping_comparisons": comparisons,
        "method": "2021-2023 frozen stock-to-stock predictive correlation network",
    }


def event_mask(frame: pd.DataFrame, family: str) -> pd.Series:
    if family == FAMILIES[0]:
        return frame["prediction_top1"] > 0.002
    if family == FAMILIES[1]:
        return (frame["prediction_top3"] > 0.0015) & (frame["positive_share_top3"] >= 2 / 3)
    if family == FAMILIES[2]:
        return (frame["prediction_top5"] > 0.0010) & (frame["positive_share_top5"] >= 0.60)
    if family == FAMILIES[3]:
        return (frame["prediction_top3"] > 0.002) & (frame["concentration_top3"] > 0.45)
    if family == FAMILIES[4]:
        return (frame["prediction_top3"] > 0.0015) & (frame["mean_volume_rank_top3"] > 0.80)
    raise ValueError(family)


def score(frame: pd.DataFrame, family: str) -> pd.Series:
    if family == FAMILIES[0]:
        return frame["prediction_top1"]
    if family in (FAMILIES[1], FAMILIES[3]):
        return frame["prediction_top3"] + frame["positive_share_top3"] * 0.001
    if family == FAMILIES[2]:
        return frame["prediction_top5"] + frame["positive_share_top5"] * 0.001
    if family == FAMILIES[4]:
        return frame["prediction_top3"] + frame["mean_volume_rank_top3"] * 0.001
    raise ValueError(family)


def run(args: argparse.Namespace) -> dict:
    evaluator_globals = BASE["run"].__globals__
    evaluator_globals.update(
        {
            "FAMILIES": FAMILIES,
            "FIRST_VERSION": 17009,
            "PRIOR_COMPARISONS": 542_133,
            "TOP_COUNT_BY_DECISION": None,
            "attach_training_scales": attach_leader_network,
            "event_mask": event_mask,
            "score": score,
        }
    )
    result = BASE["run"](args)
    result["campaign_id"] = "v17009-v17108-frozen-stock-leader-network"
    result["leader_network_evidence"] = result.pop("training_only_scale_evidence")
    BASE["COMMON"]["atomic_json"](Path(args.output), result)
    best = result["results_by_development_rank"][0]
    Path(args.output).with_suffix(".md").write_text(
        "# v17009-v17108 frozen stock leader network\n\n"
        f"- Status: COMPLETE; versions: {result['versions_completed']}; admitted: 0\n"
        f"- Best: v{best['version']} ({best['family']}, bar {best['decision_bar']}, hold {best['holding_minutes']}m)\n"
        + "\n".join(
            f"- {name}: annualized {value['annualized_return']:.2%}, MDD {value['max_drawdown']:.2%}, IR {value['information_ratio']:.2f}"
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
    parser.add_argument("--output", default="research/results/2026-09-07-v17009-v17108-leader-network.json")
    return parser.parse_args()


if __name__ == "__main__":
    summary = run(parse_args())
    print(json.dumps({key: summary[key] for key in ("status", "versions_completed", "pre_null_candidates", "admitted_candidates", "elapsed_seconds")}, indent=2))
