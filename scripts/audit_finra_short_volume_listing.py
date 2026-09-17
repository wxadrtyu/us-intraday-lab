"""Freeze official-index evidence for FINRA historical file availability."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from us_intraday_lab.data.finra_short_volume_listing import (
    FinraMonthlyListingHttpTransport,
    build_listing_audit,
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifests(root: Path) -> pd.DataFrame:
    paths = sorted((root / "data/staging/finra_short_volume_v1").glob("????/*.json"))
    if not paths:
        raise ValueError("FINRA_LISTING_MANIFESTS_MISSING")
    return pd.DataFrame([json.loads(path.read_text(encoding="utf-8")) for path in paths])


def render_markdown(summary: dict[str, object]) -> str:
    return "\n".join(
        [
            "# FINRA Official Listing Availability Audit",
            "",
            f"- Status: **{summary['status']}**",
            f"- Audited files: {summary['audited_files']:,}",
            f"- Late CDN timestamps: {summary['late_cdn_timestamps']:,}",
            f"- Official-index originals: {summary['official_index_originals']:,}",
            f"- Official-index updated files: {summary['official_index_updates']:,}",
            f"- Official-index missing files: {summary['official_index_missing']:,}",
            f"- Distinct official page hashes: {summary['official_page_hashes']:,}",
            f"- Audit SHA-256: `{summary['audit_sha256']}`",
            "- Paper activation: **false**",
            "- Order route: **FORBIDDEN**",
            "",
        ]
    )


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report-json", required=True, type=Path)
    parser.add_argument("--report-md", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    audit = build_listing_audit(
        load_manifests(arguments.root.resolve()),
        FinraMonthlyListingHttpTransport(
            cache_root=arguments.root.resolve()
            / "research/cache/finra_short_volume_listing_v1"
        ),
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = arguments.output.with_suffix(".tmp.parquet")
    audit.to_parquet(temporary, index=False, compression="zstd")
    temporary.replace(arguments.output)
    counts = audit["availability_evidence"].value_counts()
    summary: dict[str, object] = {
        "status": "COMPLETE",
        "training_only": True,
        "audited_files": len(audit),
        "late_cdn_timestamps": int(
            audit["availability_evidence"].ne("SAME_DAY_LAST_MODIFIED").sum()
        ),
        "official_index_originals": int(counts.get("ORIGINAL_OFFICIAL_INDEX", 0)),
        "official_index_updates": int(counts.get("UPDATED_OFFICIAL_INDEX", 0)),
        "official_index_missing": int(counts.get("NOT_LISTED_OFFICIAL_INDEX", 0)),
        "official_page_hashes": int(audit["index_sha256"].dropna().nunique()),
        "evidence_counts": {str(key): int(value) for key, value in counts.items()},
        "audit_sha256": _sha256_file(arguments.output),
        "paper_activation": False,
        "order_route": "FORBIDDEN",
    }
    arguments.report_json.parent.mkdir(parents=True, exist_ok=True)
    arguments.report_json.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    arguments.report_md.write_text(render_markdown(summary), encoding="utf-8")
    print(json.dumps(summary, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
