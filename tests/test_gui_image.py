"""A fresh desktop Tk process verifies image presentation and persistence."""

from pathlib import Path
import subprocess
import sys


def test_real_tk_image_roundtrip():
    result = subprocess.run([sys.executable, str(Path(__file__).with_name("gui_image_roundtrip.py"))],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
