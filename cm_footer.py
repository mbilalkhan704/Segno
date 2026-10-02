"""The Footer tab: a small library of saved footers.

Layout: navigation (<  Footer 2 of 3  >), the editor on top, a live preview
below (updates as you type or style), then Save / Revert / Delete / Use.

  * < and > move between saved footers. > on the LAST saved footer starts one
    new, unsaved footer - only one new footer can exist at a time, and > is
    disabled while you're on it. A new footer is only stored when you Save.
  * Revert puts the editor back to the last saved version of that footer.
  * Delete removes a footer (every footer has one).
  * 'Use this footer' chooses which footer goes under outgoing emails.
"""

import tkinter as tk
from tkinter import ttk, messagebox

from cm_richtext import RichTextEditor, has_visible_text


class FooterMixin:
    # ---- construction ----------------------------------------------------------------------
    def _build_footer_view(self, parent):
        nav = ttk.Frame(parent)
        nav.pack(fill="x", pady=(0, 8))
        nav.columnconfigure(0, minsize=44)
        nav.columnconfigure(2, minsize=44)
        self.fv_prev_btn = ttk.Button(nav, text="\u25c0", width=3, command=self._footer_prev)
        self.fv_prev_btn.grid(row=0, column=0)
        self.fv_title = ttk.Label(nav, text="", font=("Segoe UI", 12, "bold"), width=26, anchor="center")
        self.fv_title.grid(row=0, column=1, padx=6)
        self.fv_next_btn = ttk.Button(nav, text="\u25b6", width=3, command=self._footer_next)
        self.fv_next_btn.grid(row=0, column=2)
        self.fv_use_label = ttk.Label(nav, text="", style="Subtle.TLabel")
        self.fv_use_label.grid(row=0, column=3, padx=(16, 0))

        ttk.Label(parent, text="Edit", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.footer_editor = RichTextEditor(parent, lambda: self._current_theme_colors, height=7,
                                            family="Arial", on_change=self._footer_changed)
        self.footer_editor.pack(fill="both", expand=True, pady=(4, 10))
        self._rich_editors.append(self.footer_editor)

        ttk.Label(parent, text="Preview - how this footer will end an email",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.footer_live_preview = RichTextEditor(parent, lambda: self._current_theme_colors, readonly=True,
                                                  paper=True, family="Arial", height=6)
        self.footer_live_preview.pack(fill="both", expand=True, pady=(4, 10))
        self._rich_editors.append(self.footer_live_preview)

        # Action buttons: each is shown only when it applies (see _footer_update_header).
        row = ttk.Frame(parent)
        row.pack(fill="x")
        self.fv_save_btn = ttk.Button(row, text="Save", command=self._footer_save)
        self.fv_save_btn.grid(row=0, column=0, padx=(0, 6))
        self.fv_revert_btn = ttk.Button(row, text="Revert", command=self._footer_revert)
        self.fv_revert_btn.grid(row=0, column=1, padx=(0, 6))
        self.fv_delete_btn = ttk.Button(row, text="Delete", style="Danger.TButton", command=self._footer_delete)
        self.fv_delete_btn.grid(row=0, column=2, padx=(0, 6))
        self.fv_use_btn = ttk.Button(row, text="Use this footer", command=self._footer_use)
        self.fv_use_btn.grid(row=0, column=3, padx=(0, 12))
        self.fv_status = ttk.Label(row, text="", style="Subtle.TLabel")
        self.fv_status.grid(row=0, column=4, sticky="w")

    # ---- state helpers ---------------------------------------------------------------------------
    def _footer_is_dirty(self):
        if not hasattr(self, "footer_editor"):
            return False
        runs = self.footer_editor.get_runs()
        if self._fv_new and not has_visible_text(runs):
            return False
        return runs != self._fv_baseline

    @staticmethod
    def _set_visible(widget, visible):
        if visible:
            widget.grid()
        else:
            widget.grid_remove()

    def _footer_update_header(self):
        """Title, in-use badge, and which buttons make sense right now:
        Save/Revert only with unsaved edits; Delete only on a saved footer; 'Use this footer'
        only for a saved, unedited footer that isn't already in use; arrows only where they lead somewhere."""
        n = len(self.footers)
        index = n if self._fv_new else self._fv_index
        dirty = self._footer_is_dirty()
        saved_view = not self._fv_new
        in_use = saved_view and index == self.active_footer
        self.fv_title.config(text="New footer (not saved yet)" if self._fv_new else f"Footer {index + 1} of {n}")
        if self._fv_new:
            self.fv_use_label.config(text="", style="Subtle.TLabel")
        elif in_use:
            self.fv_use_label.config(text="\u2714 In use for emails", style="Good.TLabel")
        else:
            self.fv_use_label.config(text="Not in use", style="Subtle.TLabel")
        self._set_visible(self.fv_prev_btn, index > 0)
        self._set_visible(self.fv_next_btn, saved_view)
        self._set_visible(self.fv_save_btn, dirty)
        self._set_visible(self.fv_revert_btn, dirty)
        self._set_visible(self.fv_delete_btn, saved_view)
        self._set_visible(self.fv_use_btn, saved_view and not in_use and not dirty)

    def _footer_changed(self):
        """Editor edit/style change -> live preview, unsaved marker, and the buttons that now apply."""
        self.footer_live_preview.set_runs(self.footer_editor.get_runs())
        if self._footer_is_dirty():
            self.fv_status.config(text="\u25cf Unsaved changes", style="Warn.TLabel")
        else:
            self.fv_status.config(text="", style="Subtle.TLabel")
        self._footer_update_header()

    def _footer_load(self, index):
        self._fv_new, self._fv_index = False, index
        self.footer_editor.set_runs(self.footers[index])
        self._footer_after_load()

    def _footer_load_new(self):
        self._fv_new, self._fv_index = True, len(self.footers)
        self.footer_editor.set_runs([])
        self._footer_after_load()

    def _footer_after_load(self):
        self._fv_baseline = self.footer_editor.get_runs()          # normalised, same form get_runs() returns
        self.footer_live_preview.set_runs(self._fv_baseline)
        self.fv_status.config(text="", style="Subtle.TLabel")
        self._footer_update_header()
        self.footer_editor.text.focus_set()

    def _footer_confirm_leave(self):
        """True if it's OK to move away from the current footer (saving or discarding edits)."""
        if not self._footer_is_dirty():
            return True
        answer = messagebox.askyesnocancel("Unsaved footer", "This footer has unsaved changes. Save them first?")
        if answer is None:
            return False
        return self._footer_save() if answer else True

    # ---- tab open / close ----------------------------------------------------------------------------
    def _open_footer_tab(self):
        if not self.main_root_frame.winfo_ismapped():
            self._reveal_main_ui()                        # e.g. opened from Settings on the upload screen
        if not self._footer_tab_open:
            self._footer_tab_open = True
            if self.footers:
                self._footer_load(self.active_footer if 0 <= self.active_footer < len(self.footers) else 0)
            else:
                self._footer_load_new()
        self._build_view_tabs()
        self._show_view("footer")

    def _close_footer_tab(self):
        if not self._footer_confirm_leave():
            return
        self._footer_tab_open = False
        self.footer_view_frame.pack_forget()
        previous = self._view_before_footer if self._view_before_footer in ("recipients", "compose") else "recipients"
        self.current_view = previous
        self._build_view_tabs()
        if self.csv_rows:
            self._show_view(previous)
            self._refresh_footer_preview()
        else:
            self._show_upload_screen()

    # ---- actions -----------------------------------------------------------------------------------------
    def _footer_save(self):
        runs = self.footer_editor.get_runs()
        if not has_visible_text(runs):
            messagebox.showerror("Footer", "A footer can't be empty. Use Delete to remove it.")
            return False
        if self._fv_new:
            self.footers.append(runs)
            self._fv_index, self._fv_new = len(self.footers) - 1, False
            if len(self.footers) == 1 and self.active_footer < 0:
                self.active_footer = 0                     # the first footer you save is used by default
        else:
            self.footers[self._fv_index] = runs
        self._fv_baseline = self.footer_editor.get_runs()
        self._save_settings()
        self._refresh_footer_preview()
        self._footer_update_header()
        self.fv_status.config(text="\u2714 Saved", style="Good.TLabel")
        return True

    def _footer_revert(self):
        self.footer_editor.set_runs(self._fv_baseline)
        self.footer_live_preview.set_runs(self._fv_baseline)
        self.fv_status.config(text="Reverted to the last saved version.", style="Subtle.TLabel")

    def _footer_prev(self):
        index = len(self.footers) if self._fv_new else self._fv_index
        if index > 0 and self._footer_confirm_leave():
            self._footer_load(index - 1)

    def _footer_next(self):
        if self._fv_new or not self._footer_confirm_leave():
            return
        if self._fv_index < len(self.footers) - 1:
            self._footer_load(self._fv_index + 1)
        else:
            self._footer_load_new()                        # one new, unsaved footer beyond the last saved

    def _footer_delete(self):
        if self._fv_new:
            if self._footer_is_dirty() and not messagebox.askyesno("Discard", "Discard this new footer?"):
                return
            self._footer_load(len(self.footers) - 1) if self.footers else self._footer_load_new()
            return
        index = self._fv_index
        text = "Delete this footer? This can't be undone."
        if index == self.active_footer:
            text += ("\n\nIt is the footer in use - emails will go out without a footer until you "
                     "choose another one.")
        if not messagebox.askyesno("Delete footer", text):
            return
        del self.footers[index]
        if self.active_footer == index:
            self.active_footer = -1
        elif self.active_footer > index:
            self.active_footer -= 1
        self._save_settings()
        self._refresh_footer_preview()
        if self.footers:
            self._footer_load(min(index, len(self.footers) - 1))
        else:
            self._footer_load_new()
        self.fv_status.config(text="Footer deleted.", style="Subtle.TLabel")

    def _footer_use(self):
        if self._fv_new:
            return
        if self._footer_is_dirty():
            if not messagebox.askyesno("Use this footer", "Save your changes and use this footer?"):
                return
            if not self._footer_save():
                return
        self.active_footer = self._fv_index
        self._save_settings()
        self._refresh_footer_preview()
        self._footer_update_header()
        self.fv_status.config(text="\u2714 Emails will use this footer.", style="Good.TLabel")
