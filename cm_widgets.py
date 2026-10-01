"""Reusable widget builders (ported from Meraki's mck_widgets_certid)."""

import tkinter as tk
from tkinter import ttk


class WidgetsMixin:
    def _section(self, parent, title):
        frame = ttk.LabelFrame(parent, text=title, padding=8)
        frame.pack(fill="x", pady=(0, 10))
        return frame

    def _subsection(self, parent, title):
        frame = ttk.LabelFrame(parent, text=title, padding=6)
        frame.pack(fill="x", pady=(0, 8))
        return frame

    def _make_toggle(self, parent, label_text, variable, label_font=None, on_toggle=None):
        """Self-drawn checkbox (canvas box + tick) that follows the theme."""
        size = 20
        wrapper = ttk.Frame(parent)
        box = tk.Canvas(wrapper, width=size, height=size, highlightthickness=0, bd=0)
        box.pack(side="left")
        label = tk.Label(wrapper, text=label_text, font=label_font, cursor="hand2")
        label.pack(side="left", padx=(5, 0))
        state = {"enabled": True}

        def redraw():
            theme = self._current_theme_colors
            box.configure(bg=theme["bg"])
            enabled = state["enabled"]
            label.configure(bg=theme["bg"], fg=theme["text"] if enabled else theme["subtle_text"])
            box.delete("all")
            checked = variable.get()
            if not enabled:
                box.create_rectangle(2, 2, size - 2, size - 2, fill=theme["bg"], outline=theme["border"], width=2)
                if checked:
                    box.create_line(5, 10, 9, 14, fill=theme["subtle_text"], width=2, capstyle="round")
                    box.create_line(9, 14, 16, 6, fill=theme["subtle_text"], width=2, capstyle="round")
                return
            if checked:
                box.create_rectangle(2, 2, size - 2, size - 2, fill=theme["accent"], outline=theme["accent"])
                box.create_line(5, 10, 9, 14, fill="#ffffff", width=2, capstyle="round")
                box.create_line(9, 14, 16, 6, fill="#ffffff", width=2, capstyle="round")
            else:
                box.create_rectangle(2, 2, size - 2, size - 2, fill=theme["entry_bg"],
                                     outline=theme["subtle_text"], width=2)

        variable.trace_add("write", lambda *_a: redraw())

        def toggle(_event=None):
            if not state["enabled"]:
                return
            box.focus_set()
            variable.set(not variable.get())
            if on_toggle:
                on_toggle()

        def set_enabled(value):
            state["enabled"] = bool(value)
            cursor = "hand2" if state["enabled"] else "arrow"
            box.configure(cursor=cursor)
            label.configure(cursor=cursor)
            redraw()

        box.bind("<Button-1>", toggle)
        label.bind("<Button-1>", toggle)
        redraw()
        self._toggle_redraws.append(redraw)
        wrapper.set_enabled = set_enabled
        return wrapper
