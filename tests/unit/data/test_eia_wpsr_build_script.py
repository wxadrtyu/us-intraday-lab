import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / 'scripts' / 'build_eia_wpsr_training_features.py'


def test_build_script_has_explicit_root_cube_and_expected_hash_arguments():
    result = subprocess.run([sys.executable, str(SCRIPT), '--help'],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert '--root' in result.stdout
    assert '--event-cube' in result.stdout
    assert '--expected-event-sha256' in result.stdout
