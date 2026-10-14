"""Isolated GUI processes verify the real main loop and worker termination."""

from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize("failure", [None, "CORE", "MEM", "DISK", "FINAL_DISK"])
def test_real_tk_lifecycle(failure):
    script = Path(__file__).with_name("gui_lifecycle.py")
    args = [sys.executable, str(script)]
    if failure:
        args.append(failure)
    result = subprocess.run(args, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
