from datetime import date
from hashlib import sha256

import pandas as pd
import pytest

from us_intraday_lab.data.eia_wpsr_features import (
    build_release_features,
    load_training_event_cube,
)

ROWS = (
    'Commercial (Excluding SPR)',
    'Total Motor Gasoline',
    'Distillate Fuel Oil',
    'Total Stocks (Excluding SPR)',
)


def fixture_frames():
    sessions = pd.bdate_range('2021-01-04', '2021-05-31').date
    records = []
    for idx, session in enumerate(sessions):
        xle = (idx % 7 - 3) * 0.001
        for symbol, ratio in (('XLE', 1), ('AAA', 2), ('AAB', 2), ('BBB', -1)):
            records.append({'session_date': session, 'symbol': symbol, 'bar_idx': 5,
                            'session_return': xle * ratio})
            records.append({'session_date': session, 'symbol': symbol, 'bar_idx': 2,
                            'session_return': 99.0 - idx})
        if idx >= 10:
            records.append({'session_date': session, 'symbol': 'CCC', 'bar_idx': 5,
                            'session_return': xle * 5})
    releases = []
    for count, release in enumerate(pd.date_range('2021-01-06', periods=13, freq='W-WED').date, 1):
        for row in ROWS:
            releases.append({'release_date': release, 'row_name': row,
                             'difference': float(count if count < 13 else -1)})
    return pd.DataFrame(records), pd.DataFrame(releases)


def test_next_session_only_and_strictly_prior_12_release_median():
    events, releases = fixture_frames()
    states, exposures = build_release_features(events, releases)
    last = states.loc[states.release_date.eq(date(2021, 3, 31))].iloc[0]
    assert last.available_date == date(2021, 4, 1)
    assert last.crude_innovation == 7.5
    assert last.crude_draw and last.concordant_draw
    assert not states.iloc[11].crude_draw
    assert exposures.loc[exposures.release_date.eq(date(2021, 3, 31)), 'available_date'].eq(
        date(2021, 4, 1)).all()


def test_beta_uses_exactly_60_prior_paired_bar5_returns_and_excludes_xle():
    events, releases = fixture_frames()
    _, exposures = build_release_features(events, releases)
    last = exposures.loc[exposures.release_date.eq(date(2021, 3, 31))].set_index('symbol')
    assert 'XLE' not in last.index
    assert last.loc['AAA', 'beta'] == pytest.approx(2.0)
    assert last.loc['AAA', 'rank'] == 1
    assert last.loc['AAB', 'rank'] == 2
    assert last.loc['BBB', 'exclusion_reason'] == 'nonpositive_beta'
    assert last.loc['CCC', 'exclusion_reason'] == 'insufficient_pairs'
    modified = events.copy()
    modified.loc[modified.session_date.eq(date(2021, 4, 1)), 'session_return'] = 999.0
    _, changed = build_release_features(modified, releases)
    changed_last = changed.loc[changed.release_date.eq(date(2021, 3, 31))].set_index('symbol')
    assert changed_last.loc['AAA', 'beta'] == pytest.approx(last.loc['AAA', 'beta'])


def test_duplicate_bar5_symbol_session_is_invalid_not_double_counted():
    events, releases = fixture_frames()
    duplicate = pd.concat([events, events.iloc[[0]]], ignore_index=True)
    states, exposures = build_release_features(duplicate, releases)
    assert states.duplicate_bar5_keys.iloc[0] == 1
    assert exposures.loc[exposures.symbol.eq('XLE'), 'symbol'].empty


def test_out_of_training_events_are_not_used_for_exposure_or_symbols():
    events, releases = fixture_frames()
    later = pd.DataFrame([{'session_date': date(2024, 1, 2), 'symbol': 'LATER',
                           'bar_idx': 5, 'session_return': 1.0}])
    _, exposures = build_release_features(pd.concat([events, later], ignore_index=True), releases)
    assert 'LATER' not in exposures.symbol.unique()


def test_training_cube_reader_pushes_period_filter_before_feature_build(tmp_path):
    path = tmp_path / 'events.parquet'
    pd.DataFrame([
        {'session_date': date(2021, 1, 4), 'symbol': 'XLE', 'bar_idx': 5,
         'session_return': 0.01},
        {'session_date': date(2024, 1, 2), 'symbol': 'LATER', 'bar_idx': 5,
         'session_return': 999.0},
    ]).to_parquet(path)
    event_hash = sha256(path.read_bytes()).hexdigest()
    loaded = load_training_event_cube(path, event_hash)
    assert loaded.symbol.tolist() == ['XLE']
    with pytest.raises(ValueError, match='hash'):
        load_training_event_cube(path, '0' * 64)
