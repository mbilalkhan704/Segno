"""Loading a source file, choosing the certificates folder, and keeping the
per-row analysis (certificate found? email valid? already sent?) current."""

import os
from tkinter import filedialog, messagebox

from cm_constants import CERT_ID_COLUMN, NAME_HEADER_GUESSES, EMAIL_HEADER_GUESSES
from cm_upload_screen import SOURCE_FILETYPES
from cm_utils import read_tabular_file, guess_column, analyze_rows, CertIndex


class LoadingMixin:
    def _load_source_file(self, path):
        """Shared by the gate screen, 'Change source file' and drag-and-drop.
        Returns True on success; on failure an error dialog has been shown."""
        try:
            headers, rows = read_tabular_file(path)
        except Exception as exc:
            messagebox.showerror("Could not read file", str(exc))
            return False
        if not headers or not rows:
            messagebox.showerror("Empty file", "That file has no columns or no data rows.")
            return False

        self.csv_path, self.csv_headers, self.csv_rows = path, headers, rows
        self.csv_label.config(text=f"{os.path.basename(path)}  ({len(rows)} rows)")
        self.name_combo["values"] = headers
        self.email_combo["values"] = headers
        self._record_recent_file(path)

        email = guess_column(headers, EMAIL_HEADER_GUESSES, contains=("e-mail", "email", "mail"))
        name = guess_column(headers, NAME_HEADER_GUESSES, contains=("name",))
        if not name or name == email:
            name = next((h for h in headers if h != email), headers[0])
        self.name_col.set(name)
        self.email_col.set(email)

        # A fresh file: process everything, drop old locked ranges and results.
        self.row_selection_mode.set("all")
        self.row_selection_text.set("")
        self.row_selection_locked_chips = []
        self.row_send_state = {}
        self._problem_cursor = 0
        self.custom_controls_frame.pack_forget()
        self.row_selection_entry.configure(style="TEntry")
        self.lock_range_btn.config(state="disabled")
        self._refresh_locked_chips_row()
        self._populate_csv_tree()

        folder = self.cert_folders.get(path)
        if not (folder and os.path.isdir(folder)):
            guess = os.path.join(os.path.dirname(path), "certificates")
            folder = guess if os.path.isdir(guess) else None
        if folder:
            self._set_cert_folder(folder, remember=False)
        else:
            self.cert_folder, self.cert_index = None, None
            self.cert_folder_label.config(text="No folder selected")
            self._recompute_analysis()

        self._build_view_tabs()
        self._show_view("recipients")
        return True

    def _upload_data_file(self):
        path = filedialog.askopenfilename(title="Choose a source file (CSV or Excel)", filetypes=SOURCE_FILETYPES)
        if path:
            self._load_source_file(path)

    # ---- certificates folder -------------------------------------------------------------
    def _choose_cert_folder(self):
        folder = filedialog.askdirectory(title="Choose the folder with the generated certificates",
                                         initialdir=self.cert_folder or (os.path.dirname(self.csv_path) if self.csv_path else None))
        if folder:
            self._set_cert_folder(folder)

    def _set_cert_folder(self, folder, remember=True):
        self.cert_folder = folder
        self.cert_folder_label.config(text=folder)
        if remember:
            self._remember_cert_folder(folder)
        self._rescan_cert_folder()

    def _rescan_cert_folder(self):
        """(Re)read the folder - e.g. after generating more certificates in Meraki."""
        self.cert_index = CertIndex(self.cert_folder) if self.cert_folder else None
        self._recompute_analysis()

    # ---- analysis ---------------------------------------------------------------------------
    def _on_columns_changed(self):
        self._recompute_analysis()

    def _recompute_analysis(self):
        if not self.csv_rows:
            self.row_infos = []
            return
        self.row_infos = analyze_rows(self.csv_rows, self.name_col.get(), self.email_col.get(),
                                      self.cert_index, CERT_ID_COLUMN)
        self._refresh_row_selection_tags()
        self._refresh_grid_status()
        self._update_check_summary()

    def _update_check_summary(self):
        if not hasattr(self, "cert_summary_label"):
            return
        n = len(self.csv_rows)
        infos = self.row_infos
        if self.cert_folder is None or self.cert_index is None:
            self.cert_summary_label.config(text="Choose the folder with the generated certificates.",
                                           style="Subtle.TLabel")
        elif self.cert_index.error:
            self.cert_summary_label.config(text=f"Can't read that folder: {self.cert_index.error}",
                                           style="Bad.TLabel")
        else:
            found = sum(1 for i in infos if i.cert_path)
            note = ""
            if CERT_ID_COLUMN not in self.csv_headers:
                note = f"\n(No '{CERT_ID_COLUMN}' column in this file - matching by name only.)"
            if found == n:
                self.cert_summary_label.config(text=f"All {n} certificates are available" + note,
                                               style="Good.TLabel")
            else:
                k = n - found
                self.cert_summary_label.config(
                    text=f"{found} of {n} certificates are available - {k} {'is' if k == 1 else 'are'} missing" + note,
                    style="Warn.TLabel")
        if not self.email_col.get():
            self.email_summary_label.config(text="Pick the column that holds the email addresses.",
                                            style="Subtle.TLabel")
        else:
            valid = sum(1 for i in infos if i.email_ok)
            dups = sum(1 for i in infos if i.dup_email)
            extra = f" \u00b7 {dups} share an address with another row" if dups else ""
            if valid == n:
                self.email_summary_label.config(text=f"All {n} email addresses look valid" + extra,
                                                style="Good.TLabel" if not dups else "Warn.TLabel")
            else:
                self.email_summary_label.config(
                    text=f"{valid} of {n} email addresses are valid - {n - valid} empty or invalid" + extra,
                    style="Warn.TLabel")
        # Controls that only make sense in some situations are shown only then.
        any_problem = any(not i.sendable for i in infos)
        any_sent = any(i.email_ok and self.sent_log.is_sent(i.key, i.email) for i in infos)
        self._toggle_widget(self.next_problem_btn, any_problem, side="left", padx=(6, 0))
        self._toggle_widget(self.include_sent_toggle, any_sent, anchor="w", pady=(0, 6),
                            before=self.send_summary_label)
        if hasattr(self, "_update_send_summary"):
            self._update_send_summary()

    @staticmethod
    def _toggle_widget(widget, show, **pack_options):
        shown = bool(widget.winfo_manager())
        if show and not shown:
            widget.pack(**pack_options)
        elif not show and shown:
            widget.pack_forget()

    def _next_problem_row(self):
        """Scroll to the next row that can't be sent (without touching the selection)."""
        if not self.row_infos:
            return
        problems = [i.index for i in self.row_infos if not i.sendable]
        if not problems:
            messagebox.showinfo("Rows with problems", "Every row has a valid email and a certificate.")
            return
        self._show_view("recipients")
        self._problem_cursor %= len(problems)
        idx = problems[self._problem_cursor]
        self._problem_cursor += 1
        iid = str(idx)
        self.csv_tree.see(iid)
        self.csv_tree.focus(iid)
        self.row_selection_status.config(
            text=f"Problem {self._problem_cursor} of {len(problems)}: row {idx} - "
                 f"{self._row_status_text(self.row_infos[idx - 1])}")
