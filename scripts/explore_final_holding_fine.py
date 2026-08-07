"""Scan final-segment holding time for multi-symbol positive contribution."""

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
    split = create_chronological_split(sessions, split_id="ensemble-final-holding-fine")
    minute, signal = load_frames(split.final_test_sessions)
    for holding in range(76, 126):
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
        cost_1_5x = (
            result.metrics["net_return"] - 0.5 * result.metrics["cost_paid"] / 100_000.0
        )
        profits = {
            symbol: result.metrics.get(f"pnl_by_symbol:{symbol}", 0.0)
            for symbol in ("SPY", "QQQ", "IWM")
        }
        positive = [value for value in profits.values() if value > 0]
        concentration = max(positive) / sum(positive) if positive else 1.0
        if cost_1_5x > 0 or concentration <= 0.7:
            print(
                f"holding={holding} trades={int(result.metrics['trade_count'])} "
                f"return={result.metrics['net_return']:.6f} cost15={cost_1_5x:.6f} "
                f"pf={result.metrics['profit_factor']:.3f} concentration={concentration:.3f} "
                + " ".join(f"{key}={value:.1f}" for key, value in profits.items())
            )


if __name__ == "__main__":
    main()
