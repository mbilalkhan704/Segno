"""Drag-and-drop setup via tkinterdnd2 (same approach as Meraki's mck_dnd.py).
If the package isn't installed, the app degrades to browse-only."""

import tkinter as tk

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES  # type: ignore
    DND_AVAILABLE = True
except Exception:
    TkinterDnD = None
    DND_FILES = None
    DND_AVAILABLE = False

AppBase = TkinterDnD.Tk if DND_AVAILABLE else tk.Tk
