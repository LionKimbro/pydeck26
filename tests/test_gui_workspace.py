"""The outer framing is exercised in a fresh process with real Tk widgets."""

from pathlib import Path
import subprocess
import sys


def test_real_tk_workspace_controls_and_restart():
    result = subprocess.run([sys.executable, str(Path(__file__).with_name("gui_workspace.py"))],
                            capture_output=True, text=True, timeout=25)
    assert result.returncode == 0, result.stdout + result.stderr


def test_real_tk_dropdown_creation_and_control_delete():
    result = subprocess.run([sys.executable, str(Path(__file__).with_name("gui_panel_delete.py"))],
                            capture_output=True, text=True, timeout=25)
    assert result.returncode == 0, result.stdout + result.stderr
