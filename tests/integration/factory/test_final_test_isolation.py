from datetime import date, timedelta

import pandas as pd
import pytest

from us_intraday_lab.validation.splits import (
    FinalTestIsolationError,
    IsolatedChronologicalViews,
    create_chronological_split,
)


def test_selection_cannot_observe_or_reuse_final_test_data() -> None:
    sessions = tuple(date(2026, 1, 1) + timedelta(days=index) for index in range(20))
    bars = pd.DataFrame(
        {
            "session_date": sessions,
            "symbol": ["SPY"] * len(sessions),
            "score": range(len(sessions)),
        }
    )
    views = IsolatedChronologicalViews(
        bars,
        create_chronological_split(sessions, split_id="integration-split"),
    )

    views.training_view()
    selected_strategy = "late" if views.validation_view()["score"].mean() > 0 else "early"
    assert selected_strategy == "late"
    assert "final_test" not in views.access_log

    final_evaluator = views.seal_selection(
        survivor_ids=(selected_strategy,),
        selection_manifest_sha256="c" * 64,
    )
    final_evaluator.final_test_view(strategy_ids=(selected_strategy,))
    assert views.access_log.count("final_test") == 1

    with pytest.raises(FinalTestIsolationError, match="FINAL_TEST_ALREADY_CONSUMED"):
        views.validation_view()
