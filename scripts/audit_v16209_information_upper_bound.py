"""Development-only forward-return upper bound and causal feature separability audit."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd
from scipy import stats

DECISIONS = (2, 5, 11, 17, 23)
HOLDINGS = (1, 2, 4, 6)
FEATURES = ("ret1", "ret3", "vwap_dev", "range_pos", "volume_to_prior",
            "directional_efficiency", "session_return")


def metrics(returns: pd.Series) -> dict[str, float | int]:
    clean = returns.dropna().astype(float)
    wealth = (1.0 + clean).cumprod()
    total = float(wealth.iloc[-1] - 1.0)
    annual = float((1.0 + total) ** (252.0 / len(clean)) - 1.0)
    drawdown = float((1.0 - wealth / wealth.cummax()).max())
    std = float(clean.std(ddof=1))
    return {"sessions": len(clean), "total_return": total, "annualized_return": annual,
            "max_drawdown": drawdown,
            "information_ratio": float(clean.mean() / std * np.sqrt(252)) if std > 0 else 0.0}


def run(cache: Path) -> dict[str, Any]:
    con = duckdb.connect()
    events = con.execute(
        "SELECT * FROM read_parquet(?) WHERE session_date <= DATE '2025-12-31'", [str(cache)]
    ).fetch_df()
    con.close()
    events["session_date"] = pd.to_datetime(events["session_date"])
    cells: list[dict[str, Any]] = []
    correlations: list[dict[str, Any]] = []
    for decision in DECISIONS:
        subset = events.loc[events["bar_idx"] == decision].copy()
        for holding in HOLDINGS:
            exit_column = {1: "p2_open", 2: "p3_open", 4: "p5_open", 6: "p7_open"}[holding]
            subset["forward_return"] = subset[exit_column] / subset["p1_open"] - 1.0
            oos = subset.loc[(subset["session_date"] >= "2024-01-01")
                             & (subset["session_date"] <= "2025-12-31")].copy()
            oracle_daily = (oos.sort_values(["session_date", "forward_return"],
                                            ascending=[True, False])
                            .groupby("session_date", sort=False).head(10)
                            .groupby("session_date")["forward_return"].mean() - 0.0018)
            positive = oos.loc[oos["forward_return"] > 0].copy()
            positive_daily = (positive.sort_values(["session_date", "forward_return"],
                                                   ascending=[True, False])
                              .groupby("session_date", sort=False).head(10)
                              .groupby("session_date")["forward_return"].mean() - 0.0018)
            cells.append({
                "decision_bar": decision, "holding_bars": holding,
                "observations": len(oos), "positive_base_rate": float((oos["forward_return"] > 0).mean()),
                "forward_return_median": float(oos["forward_return"].median()),
                "forward_return_std": float(oos["forward_return"].std()),
                "ex_post_top10_oracle_18bp": metrics(oracle_daily),
                "ex_post_positive_top10_oracle_18bp": metrics(positive_daily),
                "admission_permitted": False,
            })
            for feature in FEATURES:
                valid = oos[[feature, "forward_return"]].replace([np.inf, -np.inf], np.nan).dropna()
                rho, p_value = stats.spearmanr(valid[feature], valid["forward_return"])
                correlations.append({"decision_bar": decision, "holding_bars": holding,
                                     "feature": feature, "spearman_rho": float(rho),
                                     "two_sided_p": float(p_value), "observations": len(valid)})
    ranked = sorted(correlations, key=lambda item: abs(item["spearman_rho"]), reverse=True)
    return {
        "schema_version": "1.0.0", "status": "COMPLETE",
        "audit_id": "v16209-information-upper-bound-audit",
        "period": "2024-2025 development only", "consumed_2026_rows_loaded": 0,
        "oracle_is_not_a_strategy": True, "admission_permitted": False,
        "cells": cells, "top_25_absolute_feature_associations": ranked[:25],
    }


def main() -> None:
    cache = Path(r"E:\us-intraday-lab-data\us-market\research\cache\v14309_v14408_events.parquet")
    result = run(cache)
    output = Path("research/results/2026-09-07-v16209-information-upper-bound.json")
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, indent=2), encoding="utf-8")
    temporary.replace(output)
    best_oracle = max(result["cells"], key=lambda item: item[
        "ex_post_top10_oracle_18bp"]["annualized_return"])
    best_feature = result["top_25_absolute_feature_associations"][0]
    output.with_suffix(".md").write_text(
        "# v16209 information upper-bound audit\n\n"
        "- Scope: 2024-2025 development only; 2026 rows loaded: 0\n"
        f"- Best ex-post top-10 oracle 18bp annualized: "
        f"{best_oracle['ex_post_top10_oracle_18bp']['annualized_return']:.2%} "
        f"(bar {best_oracle['decision_bar']}, hold {best_oracle['holding_bars'] * 5}m)\n"
        f"- Strongest single causal feature association: {best_feature['feature']} rho "
        f"{best_feature['spearman_rho']:.4f} (bar {best_feature['decision_bar']}, "
        f"hold {best_feature['holding_bars'] * 5}m)\n"
        "- Oracle labels are unattainable and forbidden for admission; this audit only measures "
        "headroom and causal-feature separability.\n",
        encoding="utf-8")
    print(json.dumps({"best_oracle": best_oracle, "best_feature": best_feature}, indent=2))


if __name__ == "__main__":
    main()
