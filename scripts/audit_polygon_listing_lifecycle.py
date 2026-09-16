from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from us_intraday_lab.data.polygon_listing_lifecycle import (
    publish_lifecycle_catalog,
)


def write_immutable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text("utf-8") != content:
            raise RuntimeError(f"LIFECYCLE_AUDIT_IMMUTABLE_COLLISION:{path}")
        return
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def render_markdown(manifest: dict[str, Any]) -> str:
    permitted = "YES" if manifest["strategy_evaluation_permitted"] else "NO"
    reasons = manifest.get("rejection_reasons") or ["none"]
    reason_counts = manifest.get("exception_reason_counts") or {}
    exception_text = ", ".join(
        f"{key}={value}" for key, value in sorted(reason_counts.items())
    ) or "none"
    return "\n".join(
        [
            "# Polygon Listing Lifecycle Coverage Audit",
            "",
            f"- Dataset: `{manifest['dataset_id']}`",
            (
                f"- Coverage: {manifest['mapped_rows']:,} / "
                f"{manifest['eligible_rows']:,} "
                f"({float(manifest['coverage_ratio']):.6%})"
            ),
            f"- Exception rows: {manifest['exception_rows']:,}",
            f"- Exception reasons: {exception_text}",
            f"- Rejection reasons: {', '.join(reasons)}",
            f"- Strategy evaluation permitted: **{permitted}**",
            f"- Historical-master audit SHA-256: `{manifest['historical_master_validation_report_sha256']}`",
            f"- Universe SHA-256: `{manifest['universe_sha256']}`",
            f"- Mapping SHA-256: `{manifest['mapping_sha256']}`",
            f"- Exceptions SHA-256: `{manifest['exceptions_sha256']}`",
            "- Provider splicing: FORBIDDEN",
            "- Order route: FORBIDDEN",
            "- Paper activation: false",
            "",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit causal Polygon lifecycle coverage before strategy research."
    )
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--historical-master-audit", required=True, type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument("--output-md", required=True, type=Path)
    args = parser.parse_args()
    manifest = publish_lifecycle_catalog(
        root=args.root, validation_path=args.historical_master_audit
    )
    write_immutable(
        args.output_json,
        json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n",
    )
    write_immutable(args.output_md, render_markdown(manifest))
    print(
        json.dumps(
            {
                "dataset_id": manifest["dataset_id"],
                "eligible_rows": manifest["eligible_rows"],
                "mapped_rows": manifest["mapped_rows"],
                "exception_rows": manifest["exception_rows"],
                "coverage_ratio": manifest["coverage_ratio"],
                "strategy_evaluation_permitted": manifest[
                    "strategy_evaluation_permitted"
                ],
            },
            sort_keys=True,
        ),
        flush=True,
    )
    raise SystemExit(0 if manifest["strategy_evaluation_permitted"] else 2)


if __name__ == "__main__":
    main()
