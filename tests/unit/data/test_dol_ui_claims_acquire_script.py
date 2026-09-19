import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request

import pytest

from scripts.acquire_dol_ui_claims_training import fetch_official_with_retry

SCRIPT = Path(__file__).resolve().parents[3] / 'scripts' / 'acquire_dol_ui_claims_training.py'


def test_acquire_script_requires_explicit_stage_and_root():
    result = subprocess.run([sys.executable, str(SCRIPT), '--help'],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert '--stage {indexes,pdfs}' in result.stdout
    assert '--root ROOT' in result.stdout


def test_transient_official_502_is_retried_with_bounded_backoff():
    calls = []
    sleeps = []

    def opener(request, timeout):
        calls.append((request.full_url, timeout))
        if len(calls) < 3:
            raise HTTPError(request.full_url, 502, 'Bad Gateway', {}, None)
        return b'%PDF-valid', {'Content-Type': 'application/pdf'}, 200

    response = fetch_official_with_retry(
        Request('https://oui.doleta.gov/press/2021/020421.pdf'),
        opener=opener, sleeper=sleeps.append,
    )
    assert response[0] == b'%PDF-valid'
    assert len(calls) == 3
    assert sleeps == [2, 4]


def test_nontransient_and_exhausted_fail_closed():
    request = Request('https://oui.doleta.gov/press/2021/020421.pdf')
    sleeps = []

    def unavailable(req, timeout):
        raise HTTPError(req.full_url, 502, 'Bad Gateway', {}, None)

    with pytest.raises(HTTPError) as error:
        fetch_official_with_retry(request, opener=unavailable, sleeper=sleeps.append)
    assert error.value.code == 502
    assert sleeps == [2, 4]

    def missing(req, timeout):
        raise HTTPError(req.full_url, 404, 'Not Found', {}, None)

    sleeps.clear()
    with pytest.raises(HTTPError) as error:
        fetch_official_with_retry(request, opener=missing, sleeper=sleeps.append)
    assert error.value.code == 404
    assert sleeps == []
