"""Activate the frozen v4 winner for brokerless paper-shadow simulation."""

from __future__ import annotations

import argparse
from pathlib import Path

from us_intraday_lab.paper_shadow_activation import activate_paper_shadow


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--proposal", required=True, type=Path)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--campaign-id", required=True)
    args = parser.parse_args()
    print(
        activate_paper_shadow(
            proposal_path=args.proposal,
            selection_path=args.selection,
            database_path=args.database,
            campaign_id=args.campaign_id,
            output_root=args.root,
        )
    )


if __name__ == "__main__":
    main()
