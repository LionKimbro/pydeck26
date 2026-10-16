"""Use a fresh Tk process for Captain's Log workflow and restart checks."""

from pathlib import Path
import subprocess
import sys


def test_real_tk_captains_log():
    result = subprocess.run([sys.executable, str(Path(__file__).with_name("gui_captains_log.py"))],
                            capture_output=True, text=True, timeout=25)
    assert result.returncode == 0, result.stdout + result.stderr
