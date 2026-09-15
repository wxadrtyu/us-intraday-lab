from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from us_intraday_lab.data.sip_five_minute_research import (
    open_sip_five_minute_research_view,
)


def summarize_research_catalog(*, root: Path, audit_path: Path, role: str) -> dict[str, Any]:
    """Open the gated view and return a secret-free validation summary."""
    connection = open_sip_five_minute_research_view(root=root, audit_path=audit_path, role=role)
    try:
        row = connection.execute(
            """
            SELECT
                count(*) AS rows,
                count(DISTINCT symbol) AS symbols,
                min(session_date) AS first_session,
                max(session_date) AS last_session
            FROM research_bars
            """
        ).fetchone()
        metadata = connection.execute(
            """
            SELECT role, audit_sha256, universe_dataset_id,
                   rows_spliced, source_read_only
            FROM research_metadata
            """
        ).fetchone()
    finally:
        connection.close()
    if row is None or metadata is None:
        raise RuntimeError("SIP_FIVE_MINUTE_RESEARCH_CATALOG_EMPTY_RESULT")
    return {
        "role": metadata[0],
        "audit_sha256": metadata[1],
        "universe_dataset_id": metadata[2],
        "rows_spliced": metadata[3],
        "source_read_only": metadata[4],
        "rows": row[0],
        "symbols": row[1],
        "first_session": row[2],
        "last_session": row[3],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Open and validate an audit-gated SIP five-minute research view."
    )
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--audit", required=True, type=Path)
    parser.add_argument(
        "--role",
        required=True,
        choices=(
            "fit",
            "development_selection",
            "historical_stress_only",
            "consumed_diagnostic_only",
        ),
    )
    args = parser.parse_args()
    print(
        json.dumps(
            summarize_research_catalog(root=args.root, audit_path=args.audit, role=args.role),
            sort_keys=True,
            default=str,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
