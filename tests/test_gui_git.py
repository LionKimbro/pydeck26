"""Run Git UI checks in an isolated Tk interpreter."""

from pathlib import Path
import subprocess
import sys


def test_real_tk_git_panel():
    result = subprocess.run([sys.executable, str(Path(__file__).with_name("gui_git_panel.py"))],
                            capture_output=True, text=True, timeout=40)
    assert result.returncode == 0, result.stdout + result.stderr
