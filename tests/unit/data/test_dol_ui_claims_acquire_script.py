import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / 'scripts' / 'acquire_dol_ui_claims_training.py'


def test_acquire_script_requires_explicit_stage_and_root():
    result = subprocess.run([sys.executable, str(SCRIPT), '--help'],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert '--stage {indexes,pdfs}' in result.stdout
    assert '--root ROOT' in result.stdout
