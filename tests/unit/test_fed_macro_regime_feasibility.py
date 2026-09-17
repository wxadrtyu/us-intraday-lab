from us_intraday_lab.fed_macro_regime_feasibility import specifications


def test_fed_macro_grid_has_400_unique_cells() -> None:
    grid = specifications()

    assert len(grid) == 400
    assert len(set(grid)) == 400
