"""Audit causal FINRA short-volume coverage on the frozen training event set."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from itertools import pairwise
from pathlib import Path

import pandas as pd

from us_intraday_lab.data.quote_feature_acquisition import decision_timestamp


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def render_markdown(summary: dict[str, object]) -> str:
    years = ", ".join(str(year) for year in summary["covered_years"])
    reasons = json.dumps(summary["reason_counts"], sort_keys=True)
    return "\n".join(
        [
            "# FINRA Short-Volume Training Coverage",
            "",
            f"- Status: **{summary['status']}**",
            f"- Coverage gate: **{summary['coverage_gate']}**",
            f"- Covered event rows: {summary['covered_event_rows']:,} / {summary['event_rows']:,}",
            f"- Event coverage: {float(summary['event_coverage']):.6%}",
            f"- Covered sessions: {summary['covered_sessions']:,}",
            f"- Covered years: {years}",
            f"- Missingness evidence: `{reasons}`",
            f"- Coverage SHA-256: `{summary['coverage_sha256']}`",
            "- Development or consumed data loaded: **false**",
            f"- Paper activation: **{str(summary['paper_activation']).lower()}**",
            f"- Order route: **{summary['order_route']}**",
            "",
        ]
    )


def build_coverage(
    events: pd.DataFrame,
    daily_flow: pd.DataFrame,
    manifests: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Left-join exact-symbol prior-session flow under its publication time."""
    required = {"symbol", "session_date", "bar_idx"}
    if missing := required.difference(events.columns):
        raise ValueError(f"FINRA_EVENT_COLUMNS_MISSING:{sorted(missing)}")
    result = events.loc[:, ["symbol", "session_date", "bar_idx"]].copy()
    result["_event_order"] = range(len(result))
    result["session_date"] = pd.to_datetime(result["session_date"]).dt.date
    result["bar_idx"] = pd.to_numeric(result["bar_idx"], errors="raise").astype(int)
    if result.duplicated(["symbol", "session_date", "bar_idx"]).any():
        raise ValueError("FINRA_EVENT_KEY_DUPLICATE")
    sessions = sorted(result["session_date"].unique())
    prior_by_session = {current: prior for prior, current in pairwise(sessions)}
    result["source_date"] = result["session_date"].map(prior_by_session)
    result["decision_timestamp"] = pd.to_datetime(
        [
            decision_timestamp(session, bar_idx)
            for session, bar_idx in result.loc[:, ["session_date", "bar_idx"]].itertuples(
                index=False, name=None
            )
        ],
        utc=True,
    )

    manifest_frame = manifests.loc[:, ["trade_date", "last_modified"]].copy()
    manifest_frame["trade_date"] = pd.to_datetime(
        manifest_frame["trade_date"]
    ).dt.date
    manifest_frame["last_modified"] = pd.to_datetime(
        manifest_frame["last_modified"], utc=True
    )
    if manifest_frame["trade_date"].duplicated().any():
        raise ValueError("FINRA_MANIFEST_DATE_DUPLICATE")
    result = result.merge(
        manifest_frame,
        how="left",
        left_on="source_date",
        right_on="trade_date",
        validate="many_to_one",
        sort=False,
    ).drop(columns=["trade_date"])

    flow = daily_flow.copy()
    if not flow.empty:
        flow["trade_date"] = pd.to_datetime(flow["trade_date"]).dt.date
        if flow.duplicated(["trade_date", "symbol"]).any():
            raise ValueError("FINRA_FLOW_KEY_DUPLICATE")
    result = result.merge(
        flow,
        how="left",
        left_on=["source_date", "symbol"],
        right_on=["trade_date", "symbol"],
        validate="many_to_one",
        sort=False,
    ).drop(columns=["trade_date"])
    available = result["last_modified"].notna() & (
        result["last_modified"] < result["decision_timestamp"]
    )
    matched = result["total_volume"].notna()
    result["coverage_reason"] = "COVERED"
    result.loc[result["source_date"].isna(), "coverage_reason"] = (
        "MISSING_PRIOR_SESSION"
    )
    result.loc[
        result["source_date"].notna() & result["last_modified"].isna(),
        "coverage_reason",
    ] = "MISSING_SESSION"
    result.loc[
        result["last_modified"].notna() & ~available, "coverage_reason"
    ] = "SOURCE_NOT_YET_AVAILABLE"
    result.loc[available & ~matched, "coverage_reason"] = "SYMBOL_NOT_FOUND"
    covered = result["coverage_reason"].eq("COVERED")
    result["short_ratio"] = (result["short_volume"] / result["total_volume"]).where(
        covered
    )
    result["short_exempt_ratio"] = (
        result["short_exempt_volume"] / result["total_volume"]
    ).where(covered)
    result = result.sort_values("_event_order").drop(columns=["_event_order"])
    covered_sessions = result.loc[covered, "session_date"].nunique()
    covered_years = sorted(
        {day.year for day in result.loc[covered, "session_date"].unique()}
    )
    event_rows = len(result)
    covered_rows = int(covered.sum())
    coverage = covered_rows / event_rows if event_rows else 0.0
    gate = coverage >= 0.95 and covered_sessions >= 500 and len(covered_years) == 3
    summary: dict[str, object] = {
        "status": "COMPLETE",
        "training_only": True,
        "event_rows": event_rows,
        "covered_event_rows": covered_rows,
        "event_coverage": coverage,
        "covered_sessions": int(covered_sessions),
        "covered_years": covered_years,
        "reason_counts": {
            str(key): int(value)
            for key, value in result["coverage_reason"].value_counts().items()
        },
        "coverage_gate": "PASS" if gate else "BLOCKED",
        "development_or_consumed_loaded": False,
        "paper_activation": False,
        "order_route": "FORBIDDEN",
    }
    return result, summary


def load_staging(root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    staging = root / "data/staging/finra_short_volume_v1"
    manifest_paths = sorted(staging.glob("????/*.json"))
    manifests = pd.DataFrame(
        [json.loads(path.read_text(encoding="utf-8")) for path in manifest_paths]
    )
    partitions = [pd.read_parquet(path) for path in sorted(staging.glob("????/*.parquet"))]
    flow = pd.concat(partitions, ignore_index=True) if partitions else pd.DataFrame()
    return flow, manifests


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--events", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report-json", required=True, type=Path)
    parser.add_argument("--report-md", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    events = pd.read_parquet(
        arguments.events,
        columns=["symbol", "session_date", "bar_idx"],
        filters=[
            ("session_date", ">=", date(2021, 1, 1)),
            ("session_date", "<=", date(2023, 12, 31)),
        ],
    )
    flow, manifests = load_staging(arguments.root.resolve())
    coverage, summary = build_coverage(events, flow, manifests)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = arguments.output.with_suffix(".tmp.parquet")
    coverage.to_parquet(temporary, index=False, compression="zstd")
    temporary.replace(arguments.output)
    summary["coverage_sha256"] = _sha256_file(arguments.output)
    arguments.report_json.parent.mkdir(parents=True, exist_ok=True)
    arguments.report_json.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    arguments.report_md.write_text(render_markdown(summary), encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))
    return 0 if summary["coverage_gate"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
