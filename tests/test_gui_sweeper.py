"""Sweeper capture runs in a fresh Tk interpreter and a temporary project."""

from pathlib import Path
import subprocess
import sys


def test_real_tk_sweeper_capture():
    result = subprocess.run([sys.executable, str(Path(__file__).with_name("gui_sweeper_capture.py"))],
                            capture_output=True, text=True, timeout=25)
    assert result.returncode == 0, result.stdout + result.stderr
