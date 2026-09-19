from datetime import date

import pytest

from us_intraday_lab.data.eia_wpsr_archive import (
    ARCHIVE,
    acquire,
    discover_releases,
    discover_table4,
    parse_table4,
    preserve_raw,
)

ROOT = "https://www.eia.gov/petroleum/supply/weekly/archive/"


def issue_link(day: str) -> str:
    year = day[:4]
    return f'/petroleum/supply/weekly/archive/{year}/{day}/wpsr_{day}.php'


def test_discover_only_training_issue_links_in_date_order():
    html = ''.join(
        f'<a href="{issue_link(day)}">release</a>'
        for day in ('2023_01_05', '2020_12_30', '2021_01_06', '2022_01_05')
    ).encode()
    found = discover_releases(html)
    assert found.release_date.tolist() == [date(2021, 1, 6), date(2022, 1, 5), date(2023, 1, 5)]
    assert found.page_url.iloc[0] == ROOT + '2021/2021_01_06/wpsr_2021_01_06.php'


def test_duplicate_issue_date_rejected():
    link = issue_link('2021_01_06')
    with pytest.raises(ValueError, match='duplicate'):
        discover_releases(f'<a href="{link}">6</a><a href="{link}">6</a>'.encode())


def test_exact_page_date_and_one_same_issue_table4():
    page = ROOT + '2021/2021_01_06/wpsr_2021_01_06.php'
    html = b'<strong>Release Date:</strong>&nbsp;January 6, 2021 <a href="csv/table4.csv">CSV</a>'
    assert discover_table4(html, page) == ROOT + '2021/2021_01_06/csv/table4.csv'
    with pytest.raises(ValueError, match='date'):
        discover_table4(html.replace(b'January 6', b'January 7'), page)
    with pytest.raises(ValueError, match='Table 4'):
        discover_table4(html.replace(b'table4.csv', b'table3.csv'), page)
    with pytest.raises(ValueError, match='Table 4'):
        discover_table4(html + b'<a href="csv/table4.csv">duplicate</a>', page)
    with pytest.raises(ValueError, match='same-issue'):
        discover_table4(html.replace(b'csv/table4.csv', b'/other/table4.csv'), page)


def test_parse_four_exact_difference_rows_and_comma_numeric():
    body = (
        b'"STUB_1","1/3/20","12/27/19","Difference"\n'
        b'"Commercial (Excluding SPR)","1,001.0","1,000.0","1.000"\n'
        b'"Total Motor Gasoline","200","201","-1.000"\n'
        b'"Distillate Fuel Oil","100","99","1.000"\n'
        b'"Total Stocks (Excluding SPR)","1,300","1,301","-1.000"\n'
    )
    result = parse_table4(body, date(2021, 1, 6))
    assert len(result) == 4
    assert result.loc[result.row_name == 'Total Motor Gasoline', 'difference'].iloc[0] == -1.0
    assert result.loc[result.row_name == 'Commercial (Excluding SPR)', 'difference'].iloc[0] == 1.0
    with pytest.raises(ValueError, match='row'):
        parse_table4(body.replace(b'Distillate Fuel Oil', b'Distillate'), date(2021, 1, 6))
    with pytest.raises(ValueError, match='Difference'):
        parse_table4(body.replace(b'Difference', b'Diff'), date(2021, 1, 6))


def test_preserve_raw_never_overwrites_changed_bytes(tmp_path):
    target = tmp_path / 'issue.html'
    first = preserve_raw(target, b'first')
    assert preserve_raw(target, b'first') == first
    with pytest.raises(ValueError, match='hash'):
        preserve_raw(target, b'changed')
    assert target.read_bytes() == b'first'


def test_acquire_freezes_pages_and_urls_before_csv_fetch(tmp_path):
    issue = ROOT + '2021/2021_01_06/wpsr_2021_01_06.php'
    csv_url = ROOT + '2021/2021_01_06/csv/table4.csv'
    bodies = {
        ARCHIVE: f'<a href="{issue_link("2021_01_06")}">6</a>'.encode(),
        issue: b'<strong>Release Date:</strong>&nbsp;January 6, 2021 <a href="csv/table4.csv">CSV</a>',
        csv_url: b'not requested',
    }
    fetched = []

    def fetch(url):
        fetched.append(url)
        return bodies[url], {'etag': 'frozen'}, 200

    result = acquire(tmp_path, fetch, include_csv=False)
    assert fetched == [ARCHIVE, issue]
    assert result['releases'][0]['csv_url'] == csv_url
    assert result['releases'][0]['page_sha256']
    assert result['index_sha256']
    assert (tmp_path / 'source_manifest.json').exists()
    assert not (tmp_path / 'csv' / '2021-01-06.csv').exists()
    bodies[issue] = b'changed'
    with pytest.raises(ValueError, match='hash'):
        acquire(tmp_path, fetch, include_csv=False)


def test_csv_stage_parses_and_is_idempotent(tmp_path):
    issue = ROOT + '2021/2021_01_06/wpsr_2021_01_06.php'
    csv_url = ROOT + '2021/2021_01_06/csv/table4.csv'
    rows = (
        b'STUB_1,Difference\n'
        b'Commercial (Excluding SPR),1.0\n'
        b'Total Motor Gasoline,-2.0\n'
        b'Distillate Fuel Oil,3.0\n'
        b'Total Stocks (Excluding SPR),-4.0\n'
    )
    bodies = {
        ARCHIVE: f'<a href="{issue_link("2021_01_06")}">6</a>'.encode(),
        issue: b'Release Date: January 6, 2021 <a href="csv/table4.csv">CSV</a>',
        csv_url: rows,
    }

    def fetch(url):
        return bodies[url], {}, 200

    acquire(tmp_path, fetch)
    first = acquire(tmp_path, fetch, include_csv=True)
    assert first['csv_records'][0]['sha256']
    assert acquire(tmp_path, fetch, include_csv=True)['csv_records'] == first['csv_records']
    bodies[csv_url] = rows + b'changed'
    with pytest.raises(ValueError, match='hash'):
        acquire(tmp_path, fetch, include_csv=True)
