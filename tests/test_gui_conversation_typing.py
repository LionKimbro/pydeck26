"""Real Tk reproduces asynchronous projections between Entry edit and KeyRelease."""

from pathlib import Path
import subprocess
import sys


def test_conversation_typing_survives_delayed_core_projections():
    result = subprocess.run([sys.executable, str(Path(__file__).with_name("gui_conversation_typing.py"))],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
