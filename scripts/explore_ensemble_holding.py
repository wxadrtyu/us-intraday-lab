"""Evaluate holding-time robustness and symbol contribution for the ensemble."""

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
    split = create_chronological_split(sessions, split_id="ensemble-holding")
    frames = {
        phase: load_frames(phase_sessions)
        for phase, phase_sessions in (
            ("train", split.train_sessions),
            ("validation", split.validation_sessions),
            ("final_test", split.final_test_sessions),
        )
    }
    for holding in (108, 112, 114, 116, 117, 118):
        historical = 0
        values: list[str] = []
        for phase in ("train", "validation", "final_test"):
            minute, signal = frames[phase]
            result = run(
                definition(
                    -0.002,
                    bridge=True,
                    bridge_return_max=-0.0019,
                    bridge_return_3_max=-0.0015,
                    max_holding_minutes=holding,
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
            symbols = ",".join(
                f"{symbol}:{result.metrics.get(f'pnl_by_symbol:{symbol}', 0.0):.1f}"
                for symbol in ("SPY", "QQQ", "IWM")
            )
            values.append(
                f"{phase}=({count},{result.metrics['net_return']:.5f},"
                f"{cost_1_5x:.5f},{result.metrics['profit_factor']:.3f};{symbols})"
            )
        print(f"holding={holding} historical={historical} " + " ".join(values))


if __name__ == "__main__":
    main()
