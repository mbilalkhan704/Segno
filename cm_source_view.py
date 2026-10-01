"""Recipients grid + row selection. This is Meraki's mck_source_view
(All rows / Custom ranges, shift/ctrl-click, lockable range chips) with
three changes:
  * a Status column and a FOUR-state row colouring, because a row now has
    two independent facts: "will it be sent?" (selection) and "can it be
    sent?" (valid email + certificate found + not already sent);
  * a Meraki bug fixed (grid-click in 'All rows' mode left the custom
    controls hidden); the lock bar + chips sit below the grid, as in Meraki;
  * a 'Select sendable rows' shortcut and a colour legend."""

import os
import tkinter as tk
from datetime import datetime
from tkinter import ttk, messagebox

from cm_dnd import DND_FILES, DND_AVAILABLE as _DND_AVAILABLE

# Fixed, theme-independent semantic colours (text colour is fixed too, so it
# stays readable on these light backgrounds in dark themes).
ROW_COLORS = {
    "sel_ok":    ("#d3f9d8", "#1a2e1a", "Will be sent"),
    "sel_skip":  ("#ffe8cc", "#4a2c00", "Selected but will be skipped"),
    "unsel_ok":  ("#ffe3e3", "#3a1414", "Not selected"),
    "unsel_bad": ("#f1d3d3", "#4a2323", "Not selected (also can't be sent)"),
}


class SourceViewMixin:
    def _build_recipients_view(self, parent):
        mode_row = ttk.Frame(parent)
        mode_row.pack(fill="x", pady=(0, 4))
        self._mode_row = mode_row
        ttk.Label(mode_row, text="Rows to send to:").pack(side="left")
        ttk.Radiobutton(mode_row, text="All rows", value="all", variable=self.row_selection_mode,
                        command=self._on_row_selection_mode_changed).pack(side="left", padx=(6, 10))
        ttk.Radiobutton(mode_row, text="Custom", value="custom", variable=self.row_selection_mode,
                        command=self._on_row_selection_mode_changed).pack(side="left")
        ttk.Button(mode_row, text="Select sendable rows", command=self._select_sendable_rows
                   ).pack(side="right")

        self.custom_controls_frame = ttk.Frame(parent)
        entry_row = ttk.Frame(self.custom_controls_frame)
        entry_row.pack(fill="x")
        self.row_selection_entry = ttk.Entry(entry_row, textvariable=self.row_selection_text, width=22)
        self.row_selection_entry.pack(side="left", padx=(0, 4))
        self.row_selection_entry.bind("<KeyRelease>", lambda e: self._on_row_selection_text_changed())
        self.lock_range_btn = ttk.Button(entry_row, text="Lock", width=10,
                                         command=self._lock_current_range, state="disabled")
        self.lock_range_btn.pack(side="left")
        ttk.Label(self.custom_controls_frame,
                  text='Type a range ("2-5, 8, 10-12") or shift/ctrl-click rows below, '
                       'then click "Lock" to protect it before starting another.',
                  style="Subtle.TLabel", wraplength=520, justify="left").pack(anchor="w", pady=(2, 2))
        ttk.Label(self.custom_controls_frame, text="Locked ranges:", style="Subtle.TLabel").pack(anchor="w", pady=(2, 0))
        theme = self._current_theme_colors
        self.chips_outer = tk.Frame(self.custom_controls_frame, height=34, bg=theme["bg"])
        self.chips_outer.pack(fill="x", pady=(0, 6))
        self.chips_outer.pack_propagate(False)
        self.chips_canvas = tk.Canvas(self.chips_outer, height=30, highlightthickness=0, bg=theme["bg"])
        chips_hsb = ttk.Scrollbar(self.chips_outer, orient="horizontal", command=self.chips_canvas.xview)
        self.chips_canvas.configure(xscrollcommand=chips_hsb.set)
        self.chips_canvas.pack(side="top", fill="x")
        self.chips_inner = tk.Frame(self.chips_canvas, bg=theme["bg"])
        self.chips_canvas.create_window((0, 0), window=self.chips_inner, anchor="nw")
        self.chips_inner.bind("<Configure>", lambda e: self.chips_canvas.configure(
            scrollregion=self.chips_canvas.bbox("all")))

        def _chips_wheel(event):
            if getattr(event, "num", None) == 4:
                self.chips_canvas.xview_scroll(-1, "units")
            elif getattr(event, "num", None) == 5:
                self.chips_canvas.xview_scroll(1, "units")
            else:
                self.chips_canvas.xview_scroll(int(-1 * (event.delta / 120)), "units")
            return "break"

        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.chips_canvas.bind(seq, _chips_wheel)
        self._refresh_locked_chips_row()

        # Status line + legend (always visible, unlike the custom controls)
        info_row = ttk.Frame(parent)
        info_row.pack(fill="x", pady=(2, 2))
        self.row_selection_status = ttk.Label(info_row, text="", style="Subtle.TLabel")
        self.row_selection_status.pack(side="left")
        self.legend_frame = tk.Frame(info_row, bg=theme["bg"])
        self.legend_frame.pack(side="right")
        self._legend_labels = []
        for key, (bg, fg, text) in ROW_COLORS.items():
            lbl = tk.Label(self.legend_frame, text=f" {text} ", bg=bg, fg=fg, font=("Segoe UI", 8), padx=3)
            lbl.pack(side="left", padx=(6, 0))
            self._legend_labels.append(lbl)

        grid_frame = ttk.Frame(parent)
        grid_frame.pack(fill="both", expand=True)
        grid_frame.rowconfigure(0, weight=1)
        grid_frame.columnconfigure(0, weight=1)
        self.csv_tree = ttk.Treeview(grid_frame, show="headings", selectmode="extended")
        vsb = ttk.Scrollbar(grid_frame, orient="vertical", command=self.csv_tree.yview)
        hsb = ttk.Scrollbar(grid_frame, orient="horizontal", command=self.csv_tree.xview)
        self.csv_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.csv_tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        for tag, (bg, fg, _t) in ROW_COLORS.items():
            self.csv_tree.tag_configure(tag, background=bg, foreground=fg)
        self.csv_tree.bind("<<TreeviewSelect>>", self._on_csv_tree_select)

        if _DND_AVAILABLE:
            for widget in (parent, grid_frame, self.csv_tree):
                try:
                    widget.drop_target_register(DND_FILES)
                    widget.dnd_bind("<<Drop>>", self._on_source_view_drop)
                except Exception:
                    pass

    def _restyle_legend(self):
        theme = self._current_theme_colors
        self.legend_frame.configure(bg=theme["bg"])

    def _on_source_view_drop(self, event):
        path = self._first_dropped_path(event)
        if not path:
            return
        if os.path.splitext(path)[1].lower() not in (".csv", ".xlsx", ".xlsm"):
            messagebox.showerror("Unsupported file", f"'{os.path.basename(path)}' isn't a CSV or Excel file.")
            return
        self._load_source_file(path)

    # ---- grid contents ---------------------------------------------------------------------
    def _populate_csv_tree(self):
        tree = self.csv_tree
        tree.delete(*tree.get_children())
        columns = ["#", "Status"] + self.csv_headers
        tree["columns"] = columns
        for col in columns:
            tree.heading(col, text=col)
            width = 50 if col == "#" else (230 if col == "Status" else 130)
            tree.column(col, width=width, anchor="w", stretch=False)
        for i, row in enumerate(self.csv_rows, start=1):
            tree.insert("", "end", iid=str(i), values=[i, ""] + [row.get(h, "") for h in self.csv_headers])
        self._refresh_row_selection_tags()
        self._refresh_grid_status()

    @staticmethod
    def _parse_row_selection(text, max_row):
        """'2-5, 8, 10-12' -> ({2,3,4,5,8,10,11,12}, error_or_None), clipped to [1, max_row]."""
        indices, text = set(), text.strip()
        if not text:
            return set(), None
        for part in text.split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                bounds = part.split("-")
                if len(bounds) != 2:
                    return set(), f"Invalid range: '{part}'"
                try:
                    a, b = int(bounds[0]), int(bounds[1])
                except ValueError:
                    return set(), f"Invalid range: '{part}'"
                if a > b:
                    a, b = b, a
                indices.update(n for n in range(a, b + 1) if 1 <= n <= max_row)
            else:
                try:
                    n = int(part)
                except ValueError:
                    return set(), f"Invalid row number: '{part}'"
                if 1 <= n <= max_row:
                    indices.add(n)
        return indices, None

    @staticmethod
    def _compress_indices_to_range_string(indices):
        if not indices:
            return ""
        nums = sorted(indices)
        parts, start = [], nums[0]
        prev = start
        for n in nums[1:]:
            if n == prev + 1:
                prev = n
                continue
            parts.append(str(start) if start == prev else f"{start}-{prev}")
            start = prev = n
        parts.append(str(start) if start == prev else f"{start}-{prev}")
        return ", ".join(parts)

    def _get_selected_row_indices(self):
        """Rows the user chose: every locked chip UNION the live text box
        ('All rows' or an empty file = every row)."""
        max_row = len(self.csv_rows)
        if max_row == 0:
            return set()
        if self.row_selection_mode.get() == "all":
            return set(range(1, max_row + 1))
        result = set()
        for chip in self.row_selection_locked_chips:
            result |= chip["indices"]
        live, _err = self._parse_row_selection(self.row_selection_text.get(), max_row)
        return result | live

    # ---- colouring & status ----------------------------------------------------------------
    def _is_effectively_sendable(self, info):
        if not info.sendable:
            return False
        return self.include_sent.get() or not self.sent_log.is_sent(info.key, info.email)

    def _row_status_text(self, info):
        state = self.row_send_state.get(info.index)
        if state:
            kind, detail = state
            if kind == "sent":
                return "\u2714 Sent just now"
            if kind == "failed":
                return "\u2716 Failed: " + (detail[:70] + "\u2026" if len(detail) > 70 else detail)
            if kind == "queued":
                return "\u23f3 Queued"
            if kind == "sending":
                return "\u23f3 Sending\u2026"
            return "\u2014 Not attempted"
        if not self.email_col.get():
            return "\u2014 Pick the email column"
        if self.cert_index is None:
            return "\u2014 Pick the certificates folder"
        if info.email_ok:
            entry = self.sent_log.get(info.key, info.email)
            if entry:
                try:
                    when = datetime.fromisoformat(entry.get("sent_at", "")).strftime("%d %b %H:%M")
                except ValueError:
                    when = ""
                return f"\u2714 Sent {when}".strip()
        problems = []
        if info.cert_reason == "no name":
            problems.append("No name")
        elif info.cert_reason == "no certificate":
            problems.append("No certificate")
        if not info.email_ok:
            problems.append({"empty": "No email", "invalid": "Invalid email"}.get(info.email_reason, "Bad email"))
        if problems:
            return "\u2716 " + " \u00b7 ".join(problems)
        notes = []
        if info.match_how == "id":
            notes.append("matched by ID: " + os.path.basename(info.cert_path))
        if info.dup_email:
            notes.append("duplicate email")
        return "\u26a0 Ready - " + "; ".join(notes) if notes else "\u2714 Ready"

    def _refresh_grid_status(self):
        if not hasattr(self, "csv_tree"):
            return
        for info in self.row_infos:
            iid = str(info.index)
            if self.csv_tree.exists(iid):
                self.csv_tree.set(iid, "Status", self._row_status_text(info))

    def _update_row_status(self, row_index):
        info = self.row_infos[row_index - 1] if 0 < row_index <= len(self.row_infos) else None
        iid = str(row_index)
        if info and self.csv_tree.exists(iid):
            self.csv_tree.set(iid, "Status", self._row_status_text(info))

    def _refresh_row_selection_tags(self):
        if not hasattr(self, "csv_tree"):
            return
        total = len(self.csv_rows)
        selected = self._get_selected_row_indices()
        eff = {info.index for info in self.row_infos if self._is_effectively_sendable(info)}
        for i in range(1, total + 1):
            iid = str(i)
            if not self.csv_tree.exists(iid):
                continue
            ok = i in eff
            tag = ("sel_ok" if ok else "sel_skip") if i in selected else ("unsel_ok" if ok else "unsel_bad")
            self.csv_tree.item(iid, tags=(tag,))
        self.row_selection_status.config(
            text=f"{len(selected)} of {total} row(s) selected \u00b7 {len(selected & eff)} will be sent")
        if hasattr(self, "_update_send_summary"):
            self._update_send_summary()

    def _select_sendable_rows(self):
        eff = {info.index for info in self.row_infos if self._is_effectively_sendable(info)}
        if not eff:
            messagebox.showinfo("Select sendable rows",
                                "No rows are ready to send yet. Check the email column and the "
                                "certificates folder first.")
            return
        self.row_selection_locked_chips = []
        self._refresh_locked_chips_row()
        self.row_selection_text.set(self._compress_indices_to_range_string(eff))
        self.row_selection_mode.set("custom")
        self._on_row_selection_mode_changed()

    # ---- Meraki's selection machinery (unchanged logic) ---------------------------------------
    def _update_custom_entry_validity(self):
        if not hasattr(self, "row_selection_entry"):
            return
        indices, err = self._parse_row_selection(self.row_selection_text.get().strip(), len(self.csv_rows))
        self.row_selection_entry.configure(style="Invalid.TEntry" if err else "TEntry")
        if hasattr(self, "lock_range_btn"):
            self.lock_range_btn.config(state="normal" if (indices and not err) else "disabled")

    def _on_row_selection_mode_changed(self):
        if self.row_selection_mode.get() == "all":
            self.custom_controls_frame.pack_forget()
            self._row_selection_syncing = True
            self.csv_tree.selection_remove(self.csv_tree.selection())
            # <<TreeviewSelect>> fires asynchronously - release the guard on the
            # next idle pass so a deferred event can still see it set.
            self.after_idle(lambda: setattr(self, "_row_selection_syncing", False))
        else:
            self.custom_controls_frame.pack(fill="x", pady=(6, 0))   # packed after the grid -> sits below it
            self._update_custom_entry_validity()
        self._refresh_row_selection_tags()

    def _on_row_selection_text_changed(self):
        # Local-only on purpose: never mirrors typed text into the grid's native
        # selection (that created an async feedback loop in Meraki).
        self._update_custom_entry_validity()
        self._refresh_row_selection_tags()

    def _lock_current_range(self):
        total = len(self.csv_rows)
        indices, err = self._parse_row_selection(self.row_selection_text.get().strip(), total)
        if err:
            messagebox.showerror("Invalid range", err)
            return
        if not indices:
            messagebox.showerror("Nothing to lock in", "Type a range or shift/ctrl-click rows in the grid first.")
            return
        locked = set()
        for chip in self.row_selection_locked_chips:
            locked |= chip["indices"]
        overlap = indices & locked
        if overlap:
            messagebox.showerror(
                "Row(s) already locked",
                f"Row(s) {self._compress_indices_to_range_string(overlap)} are already part of a locked "
                f"range. Remove that range first (its '\u2212' button) or adjust your selection.")
            return
        self.row_selection_mode.set("custom")
        self.row_selection_locked_chips.append(
            {"indices": frozenset(indices), "label": self._compress_indices_to_range_string(indices)})
        self._refresh_locked_chips_row()
        self._row_selection_syncing = True
        self.row_selection_text.set("")
        self.csv_tree.selection_remove(self.csv_tree.selection())
        self.after_idle(lambda: setattr(self, "_row_selection_syncing", False))
        self._update_custom_entry_validity()
        self._refresh_row_selection_tags()

    def _refresh_locked_chips_row(self):
        if not hasattr(self, "chips_inner"):
            return
        for w in self.chips_inner.winfo_children():
            w.destroy()
        theme = self._current_theme_colors
        if not self.row_selection_locked_chips:
            tk.Label(self.chips_inner, text="(none yet)", bg=theme["bg"], fg=theme["subtle_text"],
                     font=("Segoe UI", 8)).pack(side="left", padx=4, pady=6)
        else:
            for idx, chip in enumerate(self.row_selection_locked_chips):
                pill = tk.Frame(self.chips_inner, bg=theme["accent"])
                pill.pack(side="left", padx=3, pady=3)
                tk.Label(pill, text=chip["label"], bg=theme["accent"], fg="#ffffff",
                         font=("Segoe UI", 8, "bold"), padx=6, pady=3).pack(side="left")
                rm = tk.Label(pill, text=" \u2212 ", bg=theme["accent2"], fg="#ffffff",
                              font=("Segoe UI", 9, "bold"), cursor="hand2")
                rm.pack(side="left", fill="y")
                rm.bind("<Button-1>", lambda e, i=idx: self._remove_locked_chip(i))
        self.chips_inner.update_idletasks()
        self.chips_canvas.configure(scrollregion=self.chips_canvas.bbox("all"))

    def _remove_locked_chip(self, index):
        if 0 <= index < len(self.row_selection_locked_chips):
            del self.row_selection_locked_chips[index]
            self._refresh_locked_chips_row()
            self._refresh_row_selection_tags()

    def _on_csv_tree_select(self, _event=None):
        if self._row_selection_syncing:
            return
        sel = self.csv_tree.selection()
        if not sel:
            return
        self.row_selection_mode.set("custom")
        self.row_selection_text.set(self._compress_indices_to_range_string(sorted(int(i) for i in sel)))
        # Meraki bug fix: switching the variable alone leaves the custom
        # controls hidden - run the full mode-change handler instead.
        self._on_row_selection_mode_changed()
