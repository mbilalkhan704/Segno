"""Theme application: styles every ttk widget and recolors the custom ones.
Ported from Meraki's DialogsMixin._apply_theme_impl."""

import ctypes
import sys
import tkinter as tk
from tkinter import ttk

from cm_constants import THEMES, DEFAULT_THEME


class ThemingMixin:
    def _apply_theme(self, name):
        locked = False
        if sys.platform.startswith("win") and self.winfo_viewable():
            try:
                locked = bool(ctypes.windll.user32.LockWindowUpdate(self._hwnd(self)))
            except Exception:
                locked = False
        try:
            self._apply_theme_impl(name)
            self.update_idletasks()
        finally:
            if locked:
                ctypes.windll.user32.LockWindowUpdate(0)

    def _apply_theme_impl(self, name):
        theme = THEMES.get(name, THEMES[DEFAULT_THEME])
        self._current_theme_colors = theme
        self.theme.set(name)
        self.configure(bg=theme["bg"])
        for d in self._active_modal_dialogs:
            try:
                if d.winfo_exists():
                    d.configure(bg=theme["dialog_bg"])
            except Exception:
                pass
        self._recolor_upload_background()

        if hasattr(self, "title_frame"):
            self.title_frame.config(bg=theme["toolbar_bg"])
            if getattr(self, "toolbar_icon_label", None) is not None:
                self.toolbar_icon_label.config(bg=theme["toolbar_bg"])
            self.brand_label.config(bg=theme["toolbar_bg"], fg=theme["toolbar_fg"])
            self.sub_label.config(bg=theme["toolbar_bg"], fg=theme.get("toolbar_sub", theme["toolbar_fg"]))
        if hasattr(self, "toolbar"):
            self.toolbar.configure(bg=theme["toolbar_bg"])
            for btn, key in ((self.settings_btn, "accent"), (self.issues_btn, "accent"),
                             (self.how_to_use_btn, "accent2")):
                btn.configure(bg=theme[key], fg="#ffffff", activebackground=theme[key + "_active"],
                              activeforeground="#ffffff", highlightthickness=0)
        if hasattr(self, "left_canvas"):
            self.left_canvas.configure(bg=theme["bg"])
        if hasattr(self, "footer_bar"):
            self.footer_bar.configure(bg=theme["bg"])
            self.footer_note.configure(bg=theme["bg"], fg=theme["subtle_text"])
        for redraw in list(self._toggle_redraws):
            try:
                redraw()
            except tk.TclError:
                pass

        style = ttk.Style(self)
        if style.theme_use() != "clam":
            try:
                style.theme_use("clam")
            except tk.TclError:
                pass
        style.configure("TFrame", background=theme["bg"])
        style.configure("TLabelframe", background=theme["bg"], bordercolor=theme["accent2"], borderwidth=2)
        style.configure("TLabelframe.Label", background=theme["bg"], foreground=theme["accent2_active"],
                        font=("Segoe UI", 10, "bold"))
        style.configure("TLabel", background=theme["bg"], foreground=theme["text"])
        style.configure("Subtle.TLabel", background=theme["bg"], foreground=theme["subtle_text"])
        style.configure("Good.TLabel", background=theme["bg"], foreground="#2f9e44")
        style.configure("Warn.TLabel", background=theme["bg"], foreground="#e8890c")
        style.configure("Bad.TLabel", background=theme["bg"], foreground="#e03131")
        style.configure("TButton", background=theme["accent"], foreground="#ffffff", padding=6,
                        borderwidth=0, focuscolor=theme["accent"])
        style.map("TButton",
                  background=[("active", theme["accent_active"]), ("disabled", theme["border"])],
                  foreground=[("disabled", theme["subtle_text"])],
                  focuscolor=[("active", theme["accent_active"]), ("disabled", theme["border"])])
        style.configure("Danger.TButton", background="#e03131", foreground="#ffffff", padding=6, borderwidth=0)
        style.map("Danger.TButton", background=[("active", "#c92a2a"), ("disabled", theme["border"])])
        style.configure("Dialog.TFrame", background=theme["dialog_bg"])
        style.configure("Dialog.TLabel", background=theme["dialog_bg"], foreground=theme["text"])
        style.configure("DialogSubtle.TLabel", background=theme["dialog_bg"], foreground=theme["subtle_text"])
        style.configure("TCheckbutton", background=theme["bg"], foreground=theme["text"], focuscolor=theme["bg"])
        style.configure("Dialog.TCheckbutton", background=theme["dialog_bg"], foreground=theme["text"],
                        focuscolor=theme["dialog_bg"])
        style.configure("TRadiobutton", background=theme["bg"], foreground=theme["text"], focuscolor=theme["bg"])
        style.map("TRadiobutton",
                  indicatorbackground=[("selected", theme["accent"]), ("!selected", theme["entry_bg"])],
                  indicatorforeground=[("selected", "#ffffff"), ("!selected", theme["entry_bg"])])
        style.configure("TCombobox", fieldbackground=theme["entry_bg"], background=theme["entry_bg"],
                        foreground=theme["text"], arrowcolor=theme["text"])
        style.map("TCombobox",
                  fieldbackground=[("readonly", theme["entry_bg"]), ("!readonly", theme["entry_bg"])],
                  foreground=[("readonly", theme["text"]), ("!readonly", theme["text"])],
                  selectbackground=[("readonly", theme["entry_bg"]), ("!readonly", theme["entry_bg"])],
                  selectforeground=[("readonly", theme["text"]), ("!readonly", theme["text"])],
                  arrowcolor=[("readonly", theme["text"]), ("!readonly", theme["text"])])
        style.configure("TEntry", fieldbackground=theme["entry_bg"], foreground=theme["text"])
        style.configure("Invalid.TEntry", fieldbackground=theme["invalid_bg"], foreground=theme["text"],
                        bordercolor=theme["invalid_border"])
        style.map("Invalid.TEntry", fieldbackground=[("focus", theme["invalid_bg"])],
                  bordercolor=[("focus", theme["invalid_border"])])
        style.configure("TSpinbox", fieldbackground=theme["entry_bg"], foreground=theme["text"])
        style.configure("TProgressbar", background=theme["accent"], troughcolor=theme["border"])
        style.configure("TSeparator", background=theme["border"])
        for orient in ("Horizontal", "Vertical"):
            style.configure(f"{orient}.TScrollbar", background=theme["accent"], troughcolor=theme["bg"],
                            bordercolor=theme["border"])
        self.option_add("*TCombobox*Listbox.background", theme["entry_bg"])
        self.option_add("*TCombobox*Listbox.foreground", theme["text"])
        self.option_add("*TCombobox*Listbox.selectBackground", theme["accent"])
        self.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
        style.configure("Treeview", background=theme["entry_bg"], fieldbackground=theme["entry_bg"],
                        foreground=theme["text"], rowheight=22, bordercolor=theme["border"])
        style.map("Treeview", background=[("selected", theme["accent"])], foreground=[("selected", "#ffffff")])
        style.configure("Treeview.Heading", background=theme["accent2"], foreground="#ffffff",
                        font=("Segoe UI", 9, "bold"))
        style.map("Treeview.Heading", background=[("active", theme["accent2_active"])])

        if hasattr(self, "view_tabs_bar"):
            self._restyle_view_tabs()
        if hasattr(self, "upload_dropzone"):
            self._draw_upload_dropzone()
        if hasattr(self, "chips_inner"):
            self.chips_outer.configure(bg=theme["bg"])
            self.chips_canvas.configure(bg=theme["bg"])
            self.chips_inner.configure(bg=theme["bg"])
            self._refresh_locked_chips_row()
        if hasattr(self, "recent_files_frame"):
            self._refresh_recent_files_list()
        if hasattr(self, "legend_frame"):
            self._restyle_legend()
        for ed in list(self._rich_editors):
            try:
                ed.apply_theme()
            except tk.TclError:
                pass
