"""Aggregate development-only cost and delay budgets for completed full-market batches."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIRST = 14309
LAST = 15808


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary.replace(path)


def load_records(results_dir: Path) -> tuple[list[dict[str, Any]], list[str]]:
    records: dict[int, dict[str, Any]] = {}
    sources: list[str] = []
    for path in sorted(results_dir.glob("2026-09-06-v*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        batch = payload.get("results_by_development_rank")
        if not isinstance(batch, list):
            continue
        used = False
        for item in batch:
            version = int(item.get("version", -1))
            if FIRST <= version <= LAST:
                if version in records:
                    raise RuntimeError(f"duplicate version {version} in {path}")
                records[version] = item
                used = True
        if used:
            sources.append(path.name)
    expected = set(range(FIRST, LAST + 1))
    missing = sorted(expected.difference(records))
    if missing:
        raise RuntimeError(f"incomplete audit scope; missing {len(missing)} versions, first={missing[:5]}")
    return [records[version] for version in sorted(records)], sources


def audit(results_dir: Path) -> dict[str, Any]:
    records, sources = load_records(results_dir)
    rows: list[dict[str, Any]] = []
    for item in records:
        oos = item["development_oos"]
        standard = float(oos["standard_9bp"]["annualized_return"])
        cost18 = float(oos["cost_18bp"]["annualized_return"])
        delay = float(oos["delay_5m_9bp"]["annualized_return"])
        rows.append({
            "version": item["version"], "family": item["family"],
            "signal_sessions": int(item.get("signal_sessions", oos["standard_9bp"]["sessions"])),
            "standard_9bp_annualized": standard, "cost_18bp_annualized": cost18,
            "delay_5m_9bp_annualized": delay,
            "cost_9bp_increment_annualized_loss": standard - cost18,
            "delay_5m_annualized_loss": standard - delay,
            "shortfall_to_50pct_after_18bp": 0.50 - cost18,
            "worst_scenario_annualized": min(standard, cost18, delay),
        })
    ranked = sorted(rows, key=lambda row: row["worst_scenario_annualized"], reverse=True)
    best = ranked[0]
    positive_all = sum(row["worst_scenario_annualized"] > 0 for row in rows)
    cost_robust = sum(row["cost_9bp_increment_annualized_loss"] < 0.03 for row in rows)
    result = {
        "schema_version": "1.0.0", "status": "COMPLETE",
        "audit_id": "v14309-v15808-cost-budget-audit", "versions_audited": len(rows),
        "source_files": sources, "consumed_fields_used_for_ranking": False,
        "summary": {
            "versions_positive_in_all_three_scenarios": positive_all,
            "versions_with_less_than_3pct_annualized_loss_per_extra_9bp": cost_robust,
            "best_worst_scenario": best,
            "minimum_required_improvement_to_50pct_after_18bp": best[
                "shortfall_to_50pct_after_18bp"],
        },
        "top_25_by_worst_scenario": ranked[:25],
    }
    return result


def main() -> None:
    results_dir = Path("research/results")
    result = audit(results_dir)
    output = results_dir / "2026-09-06-v14309-v15808-cost-budget-audit.json"
    atomic_write(output, result)
    best = result["summary"]["best_worst_scenario"]
    output.with_suffix(".md").write_text(
        "# v14309-v15808 development-only cost budget audit\n\n"
        f"- Versions audited: {result['versions_audited']}\n"
        f"- Positive in all three scenarios: "
        f"{result['summary']['versions_positive_in_all_three_scenarios']}\n"
        f"- Best worst-scenario version: v{best['version']} ({best['family']})\n"
        f"- Annualized standard / 18bp / delay: {best['standard_9bp_annualized']:.2%} / "
        f"{best['cost_18bp_annualized']:.2%} / {best['delay_5m_9bp_annualized']:.2%}\n"
        f"- Extra 9bp annualized loss: {best['cost_9bp_increment_annualized_loss']:.2%}\n"
        f"- Shortfall to 50% after 18bp: {best['shortfall_to_50pct_after_18bp']:.2%}\n"
        "- 2026 consumed diagnostics were not used for ranking. This audit cannot admit a strategy.\n",
        encoding="utf-8")
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
