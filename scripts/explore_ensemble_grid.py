"""Bounded development-only grid around the causal ensemble sample bridge."""

from __future__ import annotations

from diagnose_ensemble_filter import ROOT, definition, load_frames, run

from us_intraday_lab.data.catalog import connect_catalog
from us_intraday_lab.validation.splits import create_chronological_split


def main() -> None:
    with connect_catalog(root=ROOT) as connection:
        sessions = tuple(
            row[0]
            for row in connection.execute(
                "SELECT DISTINCT session_date FROM bars_15m "
                "WHERE symbol IN ('SPY', 'QQQ', 'IWM') AND session_date >= DATE '2026-04-13' "
                "ORDER BY session_date"
            ).fetchall()
        )
    split = create_chronological_split(sessions, split_id="ensemble-grid")
    frames = {
        phase: load_frames(phase_sessions)
        for phase, phase_sessions in (
            ("train", split.train_sessions),
            ("validation", split.validation_sessions),
            ("final_test", split.final_test_sessions),
        )
    }
    for return_max in (-0.0019, -0.00185, -0.0018):
        for return_3_max in (-0.0015, -0.00075, 0.0):
            values: list[str] = []
            historical = 0
            for phase in ("train", "validation", "final_test"):
                minute, signal = frames[phase]
                result = run(
                    definition(
                        -0.002,
                        bridge=True,
                        bridge_return_max=return_max,
                        bridge_return_3_max=return_3_max,
                    ),
                    minute,
                    signal,
                )
                count = int(result.metrics["trade_count"])
                if phase != "final_test":
                    historical += count
                cost_1_5x = (
                    result.metrics["net_return"]
                    - 0.5 * result.metrics["cost_paid"] / 100_000.0
                )
                values.append(
                    f"{phase}=({count},{result.metrics['net_return']:.5f},"
                    f"{cost_1_5x:.5f},{result.metrics['profit_factor']:.3f})"
                )
            print(
                f"return_1<{return_max:.5f} return_3<={return_3_max:.4f} "
                f"historical={historical} " + " ".join(values)
            )


if __name__ == "__main__":
    main()
