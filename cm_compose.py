"""Compose tab: subject, rich-text message (with Insert name), and the footer
picker (which saved footer goes under this send) with a preview."""

import tkinter as tk
from tkinter import ttk

from cm_richtext import RichTextEditor, runs_text, popup_name_menu


def footer_label(index, runs):
    """'2. Best regards, ORIC...' - first non-empty line, so footers are recognisable."""
    first = next((ln.strip() for ln in runs_text(runs).splitlines() if ln.strip()), "(empty)")
    return f"{index + 1}. " + (first[:34] + "\u2026" if len(first) > 34 else first)


class ComposeMixin:
    def _build_compose_view(self, parent):
        ttk.Label(parent, text="Subject", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        subject_row = ttk.Frame(parent)
        subject_row.pack(fill="x", pady=(4, 10))
        self.subject_entry = ttk.Entry(subject_row, textvariable=self.subject_var)
        self.subject_entry.pack(side="left", fill="x", expand=True)
        name_btn = ttk.Button(subject_row, text="Insert name \u25be")
        name_btn.pack(side="left", padx=(6, 0))
        name_btn.config(command=lambda: popup_name_menu(name_btn, self._insert_in_subject))

        ttk.Label(parent, text="Message", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        ttk.Label(parent, style="Subtle.TLabel", wraplength=640, justify="left",
                  text="Use \"Insert name\" to put each person's name in the subject or message - pick the "
                       "casing you want (as in the file, UPPERCASE, Title Case...). They appear as {name}, "
                       "{name:title}, etc. Subject and message are written fresh for every send."
                  ).pack(anchor="w", pady=(0, 4))
        self.message_editor = RichTextEditor(parent, lambda: self._current_theme_colors,
                                             show_insert_name=True, height=12, family="Arial")
        self.message_editor.pack(fill="both", expand=True)
        self._rich_editors.append(self.message_editor)

        foot_head = ttk.Frame(parent)
        foot_head.pack(fill="x", pady=(12, 4))
        ttk.Label(foot_head, text="Footer", font=("Segoe UI", 10, "bold")).pack(side="left")
        self.footer_combo = ttk.Combobox(foot_head, state="readonly", width=46)
        self.footer_combo.pack(side="left", padx=(8, 0))
        self.footer_combo.bind("<<ComboboxSelected>>", lambda e: self._on_footer_combo())
        ttk.Button(foot_head, text="Edit footers...", command=self._open_footer_tab).pack(side="right")
        self.footer_preview = RichTextEditor(parent, lambda: self._current_theme_colors, readonly=True,
                                             paper=True, family="Arial", height=4)
        self.footer_preview.pack(fill="x")
        self._rich_editors.append(self.footer_preview)
        self._refresh_footer_preview()

    def _insert_in_subject(self, token):
        self.subject_entry.insert("insert", token)
        self.subject_entry.focus_set()

    def _on_footer_combo(self):
        self.active_footer = self.footer_combo.current() - 1
        self._save_settings()
        self._refresh_footer_preview()

    def _refresh_footer_preview(self):
        """Sync the picker and the preview with the footer library / active footer."""
        if not hasattr(self, "footer_preview"):
            return
        self.footer_combo["values"] = ["(No footer)"] + [footer_label(i, f) for i, f in enumerate(self.footers)]
        self.footer_combo.current(self.active_footer + 1)
        runs = self._active_footer_runs()
        if runs:
            self.footer_preview.set_runs(runs)
        else:
            msg = ("(No footer will be added.)" if self.footers else
                   "(No footer yet - click \"Edit footers...\" to create one.)")
            self.footer_preview.set_runs([{"text": msg, "b": False, "i": True, "u": False,
                                           "size": None, "href": None}])
        if self._footer_tab_open:
            self._footer_update_header()
