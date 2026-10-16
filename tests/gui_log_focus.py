"""An actual Tcl-owned combobox popdown must not break the log focus callback."""

from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pydeck26 import captains_log_ui as ui


def run():
    root = tk.Tk()
    root.withdraw()
    window = tk.Toplevel(root)
    ui.initialize_context({"window": window, "send": lambda event: None, "is-closing": lambda: False})
    combo = ttk.Combobox(window, values=("One", "Two"), state="readonly")
    combo.pack()
    errors = []
    root.report_callback_exception = lambda *error: errors.append(error)
    try:
        root.update()
        popdown = str(root.tk.call("ttk::combobox::PopdownWindow", combo._w))
        root.tk.call("wm", "deiconify", popdown)
        root.tk.call("focus", "-force", popdown + ".f.l")
        root.update()
        assert str(window.tk.call("focus", "-displayof", window._w)) == popdown + ".f.l"
        try:
            window.focus_displayof()
        except KeyError as error:
            assert error.args == ("popdown",)
        else:
            raise AssertionError("Expected Tkinter's internal-widget lookup to reproduce the reported error")
        ui.control_keys.add("Control_L")
        ui.handle_when_focus_leaves_window(None)
        root.update_idletasks()
        assert not errors, errors
        assert ui.control_keys == {"Control_L"}  # Focus is still in this Tk application.
        window.destroy()
        ui.reset_control_if_unfocused()  # An idle callback after its window closes is harmless.
        assert not errors, errors
    finally:
        root.destroy()


if __name__ == "__main__":
    run()
