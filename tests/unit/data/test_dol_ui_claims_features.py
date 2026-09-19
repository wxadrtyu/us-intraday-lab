from datetime import date

import pytest

from us_intraday_lab.data.dol_ui_claims_features import extract_first_page, parse_first_page_text

FIRST_PAGE = """
For release 8:30 a.m. (ET) Thursday, January 2, 2020
In the week ending December 28, the advance figure for seasonally adjusted initial
claims was 222,000, a decrease of 2,000 from the previous week's revised level.
The advance number for seasonally adjusted insured unemployment during the week ending
December 21 was 1,728,000, an increase of 5,000 from the previous week's revised level.
"""

OFFICIAL_2021_STYLE = """
TRANSMISSION OF MATERIALS IN THIS RELEASE IS EMBARGOED UNTIL
8:30 A.M. (Eastern) Thursday, January 7, 2021
In the week ending January 2, the advance figure for seasonally adjusted initial
claims was 787,000, a decrease of 3,000 from the previous week's revised level.
The advance number for seasonally adjusted insured unemployment during the week ending
December 26 was 5,072,000, a decrease of 126,000 from the previous week's revised level.
"""


def test_first_page_extracts_only_first_published_advance_values():
    parsed = parse_first_page_text(FIRST_PAGE, date(2020, 1, 2))
    assert parsed["release_date"] == date(2020, 1, 2)
    assert parsed["release_time_et"] == "08:30"
    assert parsed["initial_sa"] == 222000
    assert parsed["insured_sa"] == 1728000


def test_official_2021_embargo_header_variant():
    parsed = parse_first_page_text(OFFICIAL_2021_STYLE, date(2021, 1, 7))
    assert parsed["initial_sa"] == 787000
    assert parsed["insured_sa"] == 5072000


def test_first_page_requires_matching_embargo_date_and_unique_values():
    with pytest.raises(ValueError, match="date mismatch"):
        parse_first_page_text(FIRST_PAGE, date(2020, 1, 9))
    with pytest.raises(ValueError, match="ambiguous initial"):
        initial_sentence = (
            "the advance figure for seasonally adjusted initial claims was 333,000."
        )
        parse_first_page_text(FIRST_PAGE + initial_sentence, date(2020, 1, 2))
    with pytest.raises(ValueError, match="insured"):
        parse_first_page_text(FIRST_PAGE.split("The advance number")[0], date(2020, 1, 2))
    with pytest.raises(ValueError, match="8:30"):
        parse_first_page_text(FIRST_PAGE.replace("8:30", "9:30"), date(2020, 1, 2))


def test_pdf_extractor_reads_only_page_one(monkeypatch):
    class Page:
        def __init__(self, text):
            self.text = text

        def extract_text(self):
            return self.text

    class Reader:
        def __init__(self, _stream):
            self.pages = [Page(FIRST_PAGE), Page(FIRST_PAGE.replace("222,000", "999,000"))]

    monkeypatch.setattr("us_intraday_lab.data.dol_ui_claims_features.PdfReader", Reader)
    parsed = extract_first_page(b"%PDF-mock", date(2020, 1, 2))
    assert parsed["initial_sa"] == 222000
    assert len(parsed["first_page_text_sha256"]) == 64
