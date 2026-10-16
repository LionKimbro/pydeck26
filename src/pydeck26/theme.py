"""Shaded phosphor-green palette and Tk/ttk presentation defaults."""

from tkinter import ttk

COLORS = {
    "app": "#07110b",
    "top": "#0c1c11",
    "panel": "#102619",
    "control": "#193923",
    "editor": "#08170e",
    "border": "#315e3d",
    "divider": "#244a30",
    "text": "#dcf5e1",
    "secondary": "#b2d5bb",
    "muted": "#8dab96",
    "accent": "#a0ffaf",
    "hover": "#285237",
    "pressed": "#356846",
    "selection": "#315f3f",
    "selection-text": "#ecfff0",
    "error-surface": "#35231d",
    "error-highlight": "#704333",
    "error-text": "#ffc2a5",
    "warning": "#efc875",
    "danger": "#f28b82",
}


def apply_theme(root):
    """Install once per Tk interpreter before constructing windows and editors."""
    root.configure(background=COLORS["app"])
    defaults = {
        "*background": COLORS["panel"], "*foreground": COLORS["text"],
        "*insertBackground": COLORS["accent"],
        "*selectBackground": COLORS["selection"], "*selectForeground": COLORS["selection-text"],
        "*activeBackground": COLORS["hover"], "*activeForeground": COLORS["accent"],
        "*highlightBackground": COLORS["border"], "*highlightColor": COLORS["accent"],
        "*disabledForeground": COLORS["muted"],
        "*Toplevel.background": COLORS["app"], "*Text.background": COLORS["editor"],
        "*Text.foreground": COLORS["text"], "*Text.inactiveSelectBackground": COLORS["selection"],
        "*Entry.background": COLORS["editor"], "*Entry.readonlyBackground": COLORS["control"],
        "*Canvas.background": COLORS["editor"], "*Scale.troughColor": COLORS["editor"],
        "*Listbox.background": COLORS["control"],
        "*TCombobox*Listbox.background": COLORS["control"],
        "*TCombobox*Listbox.foreground": COLORS["text"],
        "*TCombobox*Listbox.selectBackground": COLORS["selection"],
        "*TCombobox*Listbox.selectForeground": COLORS["selection-text"],
    }
    for pattern, value in defaults.items():
        root.option_add(pattern, value, "startupFile")

    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", background=COLORS["panel"], foreground=COLORS["text"],
                    bordercolor=COLORS["border"], lightcolor=COLORS["panel"], darkcolor=COLORS["panel"],
                    troughcolor=COLORS["editor"], selectbackground=COLORS["selection"],
                    selectforeground=COLORS["selection-text"], insertcolor=COLORS["accent"])
    style.configure("TFrame", background=COLORS["panel"])
    style.configure("TLabel", background=COLORS["panel"], foreground=COLORS["text"])
    style.configure("TButton", background=COLORS["control"], foreground=COLORS["text"], padding=(7, 4))
    style.map("TButton", background=[("disabled", COLORS["panel"]), ("pressed", COLORS["pressed"]), ("active", COLORS["hover"])],
              foreground=[("disabled", COLORS["muted"]), ("active", COLORS["accent"])])
    for name in ("TEntry", "TCombobox", "TSpinbox"):
        style.configure(name, fieldbackground=COLORS["editor"], background=COLORS["control"],
                        foreground=COLORS["text"], arrowcolor=COLORS["accent"],
                        selectbackground=COLORS["selection"], selectforeground=COLORS["selection-text"])
        style.map(name, fieldbackground=[("disabled", COLORS["panel"]), ("readonly", COLORS["control"])],
                  foreground=[("disabled", COLORS["muted"]), ("readonly", COLORS["text"])],
                  background=[("active", COLORS["hover"])], bordercolor=[("focus", COLORS["accent"])])
    style.configure("Treeview", background=COLORS["editor"], fieldbackground=COLORS["editor"],
                    foreground=COLORS["text"], rowheight=24)
    style.map("Treeview", background=[("selected", COLORS["selection"])],
              foreground=[("selected", COLORS["selection-text"])])
    style.configure("Treeview.Heading", background=COLORS["control"], foreground=COLORS["accent"], relief="flat")
    style.map("Treeview.Heading", background=[("active", COLORS["hover"]), ("pressed", COLORS["pressed"])])
    style.configure("TNotebook", background=COLORS["app"], borderwidth=0)
    style.configure("TNotebook.Tab", background=COLORS["top"], foreground=COLORS["secondary"], padding=(12, 7))
    style.map("TNotebook.Tab", background=[("selected", COLORS["control"]), ("active", COLORS["panel"])],
              foreground=[("selected", COLORS["accent"]), ("active", COLORS["text"])])
    for name in ("TCheckbutton", "TRadiobutton"):
        style.configure(name, background=COLORS["panel"], foreground=COLORS["text"],
                        indicatorbackground=COLORS["editor"], indicatorforeground=COLORS["accent"])
        style.map(name, background=[("active", COLORS["panel"])], foreground=[("disabled", COLORS["muted"])],
                  indicatorbackground=[("selected", COLORS["selection"]), ("active", COLORS["control"])])
    for name in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
        style.configure(name, background=COLORS["control"], troughcolor=COLORS["editor"],
                        arrowcolor=COLORS["secondary"], lightcolor=COLORS["control"], darkcolor=COLORS["control"])
        style.map(name, background=[("active", COLORS["hover"]), ("pressed", COLORS["pressed"])])
    style.configure("TPanedwindow", background=COLORS["divider"], sashwidth=6)
    style.configure("Sash", background=COLORS["divider"], sashthickness=6)
    style.configure("TSeparator", background=COLORS["border"])
