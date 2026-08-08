from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from us_intraday_lab.long_horizon.hf_snapshot import publish_hf_five_minute_snapshot


def _revision(worktree: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=worktree,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--start-month", required=True)
    parser.add_argument("--end-month", required=True)
    args = parser.parse_args()
    manifest = publish_hf_five_minute_snapshot(
        root=args.root,
        start_month=args.start_month,
        end_month=args.end_month,
        code_revision=_revision(Path.cwd()),
    )
    print(manifest.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
