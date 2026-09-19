
import pandas as pd
import pytest

from us_intraday_lab.eia_wpsr_feasibility import coverage_gate, specifications

FAMILIES = ('crude_draw', 'gasoline_draw', 'distillate_draw', 'total_draw',
            'concordant_draw')


def fixture_gate_inputs():
    dates = [
        *pd.date_range('2021-01-06', periods=52, freq='W-WED').date,
        *pd.date_range('2022-01-05', periods=51, freq='W-WED').date,
        *pd.date_range('2023-01-04', periods=51, freq='W-WED').date,
    ]
    states = pd.DataFrame({'release_date': dates,
                           'available_date': [day + pd.Timedelta(days=1) for day in dates]})
    for family in FAMILIES:
        states[family] = True
    exposures = pd.DataFrame(
        [(day, day + pd.Timedelta(days=1), f'S{i:03}', 1.0, '')
         for day in dates for i in range(200)],
        columns=['release_date', 'available_date', 'symbol', 'beta', 'exclusion_reason'],
    )
    manifest = {'source_hashes_verified': True,
                'source_manifest_sha256': 'a' * 64,
                'csv_manifest_sha256': 'b' * 64,
                'release_count': len(dates),
                'release_counts_by_year': {'2021': 52, '2022': 51, '2023': 51}}
    return manifest, states, exposures


def test_exactly_400_unique_frozen_specs():
    specs = specifications()
    assert len(specs) == len(set(specs)) == 400
    assert {item.family for item in specs} == set(FAMILIES)


def test_coverage_gate_passes_full_synthetic_source_and_exposure():
    manifest, states, exposures = fixture_gate_inputs()
    gate = coverage_gate(manifest, states, exposures)
    assert gate['passed']
    assert gate['eligible_symbol_release_pairs'] == 30800
    assert gate['sessions_with_150_beta_symbols'] == 154


@pytest.mark.parametrize('mutation', ['hash', 'year', 'total', 'symbols',
                                      'sessions', 'pairs', 'family', 'family_year'])
def test_each_frozen_coverage_floor_fails_closed(mutation):
    manifest, states, exposures = fixture_gate_inputs()
    if mutation == 'hash':
        manifest['csv_manifest_sha256'] = None
    elif mutation == 'year':
        states = states.drop(states.loc[states.release_date.map(lambda d: d.year == 2022)].index[:4])
        exposures = exposures.loc[exposures.release_date.isin(states.release_date)]
        manifest['release_count'] = len(states)
        manifest['release_counts_by_year']['2022'] = 47
    elif mutation == 'total':
        states = states.iloc[:149]
        exposures = exposures.loc[exposures.release_date.isin(states.release_date)]
        manifest['release_count'] = len(states)
        manifest['release_counts_by_year']['2023'] = 46
    elif mutation == 'symbols':
        exposures = exposures.loc[exposures.symbol.lt('S149')]
    elif mutation == 'sessions':
        late = set(states.available_date.iloc[99:])
        exposures = exposures.loc[~(
            exposures.available_date.isin(late) & exposures.symbol.ge('S149')
        )]
    elif mutation == 'pairs':
        exposures = exposures.iloc[:19999]
    elif mutation == 'family':
        states.loc[states.index[39:], 'crude_draw'] = False
    elif mutation == 'family_year':
        mask = states.release_date.map(lambda d: d.year == 2022)
        states.loc[mask, 'crude_draw'] = False
        states.loc[states.loc[mask].index[:9], 'crude_draw'] = True
    gate = coverage_gate(manifest, states, exposures)
    assert not gate['passed'], mutation


def test_duplicate_symbol_release_exposure_rejected():
    manifest, states, exposures = fixture_gate_inputs()
    duplicate = pd.concat([exposures, exposures.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match='duplicate'):
        coverage_gate(manifest, states, duplicate)
