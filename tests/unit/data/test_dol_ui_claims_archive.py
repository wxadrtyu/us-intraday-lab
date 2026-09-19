from datetime import date, timedelta

import pytest

from us_intraday_lab.data.dol_ui_claims_archive import (
    ARCHIVE_URL,
    acquire_pdfs,
    discover_pdf_links,
    freeze_year_indexes,
)


def links_for_year(year):
    first = date(year, 1, 7) if year == 2021 else date(year, 1, 6) if year == 2022 else date(year, 1, 5)
    return b''.join(
        f'<a href="/press/{year}/{(first + timedelta(days=7*i)):%m%d%y}.pdf">release</a>'.encode()
        for i in range(52)
    )


def test_parse_exact_official_pdf_links_and_dates():
    html = links_for_year(2021) + b'<a href="https://elsewhere.test/press/2021/010721.pdf">bad</a>'
    found = discover_pdf_links(html, 2021)
    assert len(found) == 52
    assert found.release_date.iloc[0] == date(2021, 1, 7)
    assert found.pdf_url.iloc[0] == 'https://oui.doleta.gov/press/2021/010721.pdf'


def test_duplicate_and_cross_year_links_fail_closed():
    duplicate = b'<a href="/press/2021/010721.pdf">7</a>' * 2
    with pytest.raises(ValueError, match='duplicate'):
        discover_pdf_links(duplicate, 2021)
    with pytest.raises(ValueError, match='year'):
        discover_pdf_links(b'<a href="/press/2022/010622.pdf">6</a>', 2021)


def test_freeze_three_index_responses_before_any_pdf_fetch(tmp_path):
    called = []

    def fetch(url, method, body):
        called.append((url, method, body))
        assert url == ARCHIVE_URL and method == 'POST'
        year = int(body.decode().split('year=')[1].split('&')[0])
        return links_for_year(year), {'ETag': f'y{year}'}, 200

    manifest = freeze_year_indexes(fetch, tmp_path)
    assert len(called) == 3
    assert [item['count'] for item in manifest['years']] == [52, 52, 52]
    assert len(manifest['pdfs']) == 156
    assert (tmp_path / 'source_manifest.json').exists()
    assert not (tmp_path / 'raw' / 'pdf').exists()
    assert freeze_year_indexes(fetch, tmp_path) == manifest
    (tmp_path / 'raw' / 'year_index_2022.html').write_bytes(b'tampered')
    with pytest.raises(ValueError, match='hash'):
        freeze_year_indexes(fetch, tmp_path)


def test_pdf_acquisition_refuses_missing_source_manifest(tmp_path):
    def forbidden_fetch(*_args):
        raise AssertionError('PDF fetch must not happen')

    with pytest.raises(ValueError, match='manifest'):
        acquire_pdfs(forbidden_fetch, tmp_path)
