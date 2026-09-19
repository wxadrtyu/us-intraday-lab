"""Build EIA release states and prior-XLE exposure from verified training-only inputs."""

import argparse
import json
from io import BytesIO
from pathlib import Path

from us_intraday_lab.data.eia_wpsr_archive import load_verified_snapshot, preserve_raw
from us_intraday_lab.data.eia_wpsr_features import (
    build_release_features,
    load_training_event_cube,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--event-cube", type=Path, required=True)
    parser.add_argument("--expected-event-sha256", required=True)
    args = parser.parse_args()

    releases, source = load_verified_snapshot(args.root)
    events = load_training_event_cube(args.event_cube, args.expected_event_sha256)
    symbols = set(events.symbol)
    if len(symbols) != 527 or "XLE" not in symbols:
        raise ValueError(f"frozen 527-symbol training sample mismatch: {len(symbols)}")
    states, exposures = build_release_features(events, releases)
    derived = args.root / "derived"
    hashes = {}
    for name, frame in (("release_states", states), ("exposures", exposures)):
        buffer = BytesIO()
        frame.to_parquet(buffer, index=False)
        hashes[name] = preserve_raw(derived / f"{name}.parquet", buffer.getvalue())
    manifest = {
        **source,
        "event_cube_sha256": args.expected_event_sha256,
        "sample_symbols": 527,
        "sample_scope": "coverage-limited; not full market",
        "release_states_sha256": hashes["release_states"],
        "exposures_sha256": hashes["exposures"],
        "release_state_rows": len(states),
        "exposure_rows": len(exposures),
        "post_availability_outcomes_loaded": False,
    }
    preserve_raw(derived / "feature_manifest.json",
                 (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode())
    print(json.dumps({"release_states": len(states), "exposure_rows": len(exposures),
                      "source_hashes_verified": True}, sort_keys=True))


if __name__ == "__main__":
    main()
