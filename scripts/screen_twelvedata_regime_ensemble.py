"""Freeze development selection for the Twelve Data regime ensemble."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_sha256(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _variant_id(proposal_id: str, parameters: object) -> str:
    return f"{proposal_id}-{_json_sha256(parameters)[:12]}"


def _passes(record: dict[str, Any], gates: dict[str, Any]) -> bool:
    return (
        float(record["train_annual"]) >= float(gates["minimum_train_annualized_return"])
        and float(record["validation_annual"])
        >= float(gates["minimum_validation_annualized_return"])
        and float(record["validation_ir"]) >= float(gates["minimum_validation_information_ratio"])
        and abs(float(record["validation_drawdown"])) <= float(gates["maximum_validation_drawdown"])
        and float(record["validation_profit_factor"])
        >= float(gates["minimum_validation_profit_factor"])
        and int(record["validation_trades"]) >= int(gates["minimum_validation_trades"])
        and sum(float(value) > 0.0 for value in record["folds"])
        >= int(gates["minimum_positive_validation_folds"])
        and float(record["validation_concentration"])
        <= float(gates["maximum_positive_symbol_concentration"])
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--proposal", required=True, type=Path)
    args = parser.parse_args()
    proposal_path = args.proposal.resolve()
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    if proposal["schema_version"] != "1.0.0" or proposal["direction"] != "long_only":
        raise ValueError("unsupported frozen portfolio proposal")
    research = proposal["research_data"]
    checks = {
        Path(research["train_file"]): research["train_sha256"],
        Path(research["validation_file"]): research["validation_sha256"],
        Path(research["train_file"]).parent.parent
        / "derived_daily_v2"
        / "train-features.parquet": research["train_feature_cache_sha256"],
        Path(research["validation_file"]).parent.parent
        / "derived_daily_v2"
        / "val-features.parquet": research["validation_feature_cache_sha256"],
    }
    for path, expected in checks.items():
        if _file_sha256(path) != expected:
            raise ValueError(f"research evidence hash mismatch: {path}")
    diagnostic = Path(__file__).with_name("diagnose_twelvedata_regime_ensemble.py")
    completed = subprocess.run(
        [sys.executable, str(diagnostic)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    records = []
    for line in completed.stdout.splitlines():
        if not line.startswith("{"):
            continue
        record = json.loads(line)
        if record.get("frontier") == "frozen_proposal":
            record["variant_id"] = _variant_id(proposal["proposal_id"], record["parameters"])
            records.append(record)
    expected_variants = (
        len(proposal["strength_branch"]["exit_minutes_values"])
        * len(proposal["recovery_branch"]["maximum_selected_stocks_values"])
        * len(proposal["capital_contract"]["overlap_strength_share_values"])
    )
    if (
        len(records) != expected_variants
        or len({record["variant_id"] for record in records}) != expected_variants
    ):
        raise ValueError("diagnostic did not produce the exact frozen variant set")
    gates = proposal["development_selection"]
    survivors = [record for record in records if _passes(record, gates)]
    if len(survivors) < int(gates["minimum_family_survivors"]):
        raise RuntimeError("fewer than the required frozen variants passed development")
    survivors.sort(
        key=lambda record: (
            -float(record["validation_annual"]),
            -float(record["validation_ir"]),
            record["variant_id"],
        )
    )
    proposal_hash = _json_sha256(proposal)
    experiment_id = (
        "portfolio-"
        + _json_sha256(
            {
                "proposal_sha256": proposal_hash,
                "train_sha256": research["train_sha256"],
                "validation_sha256": research["validation_sha256"],
            }
        )[:32]
    )
    output_dir = args.root.resolve() / "artifacts" / "portfolio_research" / experiment_id
    output_dir.mkdir(parents=True, exist_ok=True)
    selection: dict[str, Any] = {
        "schema_version": "1.0.0",
        "experiment_id": experiment_id,
        "proposal_id": proposal["proposal_id"],
        "proposal_sha256": proposal_hash,
        "variant_count": len(records),
        "survivor_ids": sorted(record["variant_id"] for record in survivors),
        "survivors": survivors,
        "winner_id": survivors[0]["variant_id"],
        "winner_parameters": survivors[0]["parameters"],
    }
    selection["selection_sha256"] = _json_sha256(selection)
    output = output_dir / "selection.json"
    temporary = output.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(selection, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(output)
    print(
        json.dumps(
            {
                "experiment_id": experiment_id,
                "selection_manifest": str(output),
                "survivors": len(survivors),
                "winner_id": selection["winner_id"],
                "winner_validation_annual": survivors[0]["validation_annual"],
                "winner_validation_ir": survivors[0]["validation_ir"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
