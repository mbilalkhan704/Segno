"""Sending: pre-flight checks and confirmation, the background worker (a
thread + queue polled from Tk), live per-row status, cancel, test send, and
the final summary with retry / CSV export."""

import csv
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from cm_constants import DAILY_LIMIT_FREE_GMAIL
from cm_mail import render_email, run_batch
from cm_richtext import find_unknown_placeholders, has_visible_text, runs_text
from cm_utils import attachment_filename

RETRYABLE_KINDS = ("temporary", "connection", "other", "sender")


class SendMixin:
    # ---- small status helpers ---------------------------------------------------------------
    def _update_sender_status(self):
        if not hasattr(self, "sender_status_label"):
            return
        if self.credentials_ready():
            self.sender_status_label.config(text=f"Sending as {self.sender_email.get()}", style="Good.TLabel")
        else:
            self.sender_status_label.config(
                text="No sender account yet - click here to set it up in Settings.", style="Warn.TLabel")

    def _build_plan(self):
        """Who would receive an email right now, and why the others wouldn't."""
        selected = self._get_selected_row_indices()
        jobs = []
        counts = {"not selected": 0, "no certificate": 0, "bad email": 0, "already sent": 0}
        for info in self.row_infos:
            if info.index not in selected:
                counts["not selected"] += 1
            elif not info.email_ok:
                counts["bad email"] += 1
            elif not info.cert_path:
                counts["no certificate"] += 1
            elif not self.include_sent.get() and self.sent_log.is_sent(info.key, info.email):
                counts["already sent"] += 1
            else:
                jobs.append({"row": info.index, "name": info.name, "email": info.email,
                             "cert_path": info.cert_path, "key": info.key,
                             "attach_name": attachment_filename(info.cert_path, info.cert_id)})
        return jobs, counts

    def _update_send_summary(self):
        if not hasattr(self, "send_summary_label") or not self.csv_rows:
            return
        jobs, counts = self._build_plan()
        text = f"{len(jobs)} email(s) ready to send"
        skipped = [f"{n} {why}" for why, n in counts.items() if n and why != "not selected"]
        if skipped:
            text += "\nSkipping: " + ", ".join(skipped)
        self.send_summary_label.config(text=text)

    # ---- compose validation ---------------------------------------------------------------------
    def _read_compose(self):
        """(subject, message_runs) or None after showing why not."""
        subject = self.subject_var.get().strip()
        runs = self.message_editor.get_runs()
        if not subject:
            self._show_view("compose")
            messagebox.showerror("Missing subject", "Please write the email subject in the Compose tab.")
            return None
        if not has_visible_text(runs):
            self._show_view("compose")
            messagebox.showerror("Missing message", "Please write the email message in the Compose tab.")
            return None
        return subject, runs

    def _require_sender(self):
        if self.credentials_ready():
            return True
        messagebox.showinfo(
            "Sender account required",
            "Sending needs a Gmail address and app password.\n\nClick OK to open Settings and set them up.")
        self._open_settings_dialog()
        return False

    # ---- send / test buttons ----------------------------------------------------------------------
    def _on_send_clicked(self):
        if self._sending:
            return
        if not self._require_sender():
            return
        if not self.csv_rows:
            messagebox.showerror("Missing data", "Please upload a source file first.")
            return
        if not self.name_col.get() or not self.email_col.get():
            messagebox.showerror("Missing column", "Please select the name column and the email column.")
            return
        if not self.cert_folder:
            messagebox.showerror("Missing folder", "Please choose the certificates folder.")
            return
        compose = self._read_compose()
        if compose is None:
            return
        subject, runs = compose

        self._rescan_cert_folder()                     # pick up files generated since last look
        jobs, counts = self._build_plan()
        if not jobs:
            why = ", ".join(f"{n} {w}" for w, n in counts.items() if n) or "no rows"
            messagebox.showerror("Nothing to send",
                                 f"No rows are ready to send.\n\nSkipped: {why}.\n"
                                 f"(Already-sent rows are skipped unless you tick \"Include already-sent rows\".)")
            return

        lines = [f"Send {len(jobs)} email(s) from {self.sender_email.get()}?", f"\nSubject: {subject}"]
        skipped = [f"{n} {w}" for w, n in counts.items() if n]
        if skipped:
            lines.append("Skipping: " + ", ".join(skipped))
        unknown = find_unknown_placeholders(subject + " " + runs_text(runs))
        if unknown:
            lines.append(f"\n\u26a0 Unrecognised placeholder(s) will be sent as typed: {', '.join(unknown)} "
                         f"(only {{name}} is replaced).")
        recent = self.sent_log.count_since(24)
        if recent + len(jobs) > DAILY_LIMIT_FREE_GMAIL:
            lines.append(f"\n\u26a0 This app sent {recent} email(s) in the last 24 hours; with these it would pass "
                         f"~{DAILY_LIMIT_FREE_GMAIL}, the free-Gmail daily limit. Gmail may stop the batch "
                         f"part-way (unsent rows can be retried).")
        lines.append(f"\nThis takes about {max(1, round(len(jobs) * (self.send_delay.get() + 1) / 60))} minute(s). "
                     f"Sent emails can't be recalled.")
        if not messagebox.askyesno("Confirm send", "\n".join(lines)):
            return
        self._start_send(jobs, subject, runs)

    def _on_test_send_clicked(self):
        if self._sending or not self._require_sender():
            return
        if not self.csv_rows:
            messagebox.showerror("Missing data", "Please upload a source file first.")
            return
        compose = self._read_compose()
        if compose is None:
            return
        subject, runs = compose
        info = next((i for i in self.row_infos if i.sendable), None)
        name = info.name if info else "Sample Name"
        job = {"row": None, "name": name, "email": self.sender_email.get(), "test": True,
               "cert_path": info.cert_path if info else None, "subject_prefix": "[TEST] ",
               "attach_name": attachment_filename(info.cert_path, info.cert_id) if info else None}
        extra = (f"using {name}'s certificate as the attachment" if info else
                 "without an attachment (no row is ready yet)")
        if not messagebox.askyesno("Send test", f"Send a test email to yourself ({job['email']}), {extra}?"):
            return
        self._start_send([job], subject, runs, test=True)

    # ---- worker ----------------------------------------------------------------------------------------
    def _start_send(self, jobs, subject, message_runs, test=False):
        footer = [dict(r) for r in self._active_footer_runs()]
        runs = [dict(r) for r in message_runs]
        cfg = {"email": self.sender_email.get(), "password": self.sender_password,
               "sender_name": self.sender_name.get()}

        def render(name):
            return render_email(subject, runs, footer, name)

        self._sending = True
        self._send_test = test
        self._cancel_event = threading.Event()
        self._send_queue = queue.Queue()
        self._send_subject = (subject, runs)
        self._last_results = {"sent": [], "failed": [], "skipped": [], "fatal": None, "cancelled": False}
        if not test:
            for j in jobs:
                self.row_send_state[j["row"]] = ("queued", "")
            self._refresh_grid_status()
        self.send_btn.config(state="disabled")
        self.test_btn.config(state="disabled")
        self.cancel_btn.pack(fill="x", pady=(0, 6), before=self.send_status_label)
        self.cancel_btn.config(state="normal", text="Cancel sending")
        self.send_progress.pack(fill="x", before=self.send_status_label)
        self.send_progress.config(maximum=max(1, len(jobs)), value=0)
        self.send_status_label.config(text=f"Connecting to Gmail\u2026")

        threading.Thread(
            target=run_batch, daemon=True,
            args=(jobs, cfg, render, self._send_queue.put, self._cancel_event, self.send_delay.get()),
        ).start()
        self.after(100, self._poll_send_queue)

    def _cancel_send(self):
        self._cancel_event.set()
        self.cancel_btn.config(state="disabled")
        self.send_status_label.config(text="Stopping after the current email\u2026")

    def _poll_send_queue(self):
        finished = False
        try:
            while True:
                ev = self._send_queue.get_nowait()
                self._handle_send_event(ev)
                if ev[0] == "done":
                    finished = True
                    break
        except queue.Empty:
            pass
        if finished:
            self._finish_send()
        else:
            self.after(100, self._poll_send_queue)

    def _handle_send_event(self, ev):
        kind, res = ev[0], self._last_results
        if kind == "progress":
            done, total = ev[1], ev[2]
            self.send_progress.config(value=done)
            self.send_status_label.config(text=f"Sending {done} of {total}\u2026")
        elif kind == "sent":
            job = ev[1]
            res["sent"].append(job)
            if not job.get("test"):
                self.row_send_state[job["row"]] = ("sent", "")
                self.sent_log.record(job["key"], job["email"], job["name"], os.path.basename(job["cert_path"]))
                self._update_row_status(job["row"])
        elif kind == "failed":
            job, fkind, msg = ev[1], ev[2], ev[3]
            res["failed"].append((job, fkind, msg))
            if not job.get("test"):
                self.row_send_state[job["row"]] = ("failed", msg)
                self._update_row_status(job["row"])
        elif kind == "skipped":
            job, reason = ev[1], ev[2]
            res["skipped"].append((job, reason))
            if not job.get("test"):
                self.row_send_state[job["row"]] = ("skipped", reason)
                self._update_row_status(job["row"])
        elif kind == "fatal":
            res["fatal"] = (ev[1], ev[2])
        elif kind == "cancelled":
            res["cancelled"] = True

    def _finish_send(self):
        self._sending = False
        self.send_btn.config(state="normal")
        self.test_btn.config(state="normal")
        self.cancel_btn.pack_forget()
        self.send_progress.pack_forget()
        res = self._last_results
        self.send_status_label.config(
            text=f"Done: {len(res['sent'])} sent, {len(res['failed'])} failed, {len(res['skipped'])} not attempted.")
        self._refresh_row_selection_tags()
        self._refresh_grid_status()
        self._update_check_summary()                # a send changes who counts as already sent
        if self._send_test:
            if res["sent"]:
                messagebox.showinfo("Test sent", f"Test email sent to {self.sender_email.get()}.\n"
                                                 f"Check the inbox (and the spam folder).")
            else:
                reason = (res["failed"][0][2] if res["failed"] else
                          res["fatal"][1] if res["fatal"] else "Unknown error")
                messagebox.showerror("Test failed", reason)
            return
        self._show_send_summary()

    # ---- summary dialog ----------------------------------------------------------------------------------
    def _retry_jobs(self):
        res = self._last_results
        jobs = [j for j, k, _m in res["failed"] if k in RETRYABLE_KINDS]
        jobs += [j for j, _r in res["skipped"]]
        return jobs

    def _show_send_summary(self):
        res = self._last_results
        dialog = self._new_dialog("Send summary", resizable=True)
        self._set_dialog_icon(dialog)
        frm = ttk.Frame(dialog, padding=16, style="Dialog.TFrame")
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="Send summary", font=("Segoe UI", 14, "bold"), style="Dialog.TLabel").pack(anchor="w")
        ttk.Label(frm, style="Dialog.TLabel", font=("Segoe UI", 10),
                  text=f"\u2714 Sent {len(res['sent'])}    \u2716 Failed {len(res['failed'])}    "
                       f"\u2014 Not attempted {len(res['skipped'])}").pack(anchor="w", pady=(4, 2))
        if res["fatal"]:
            ttk.Label(frm, text=f"The batch stopped early: {res['fatal'][1]}", foreground="#e03131",
                      style="Dialog.TLabel", wraplength=640, justify="left").pack(anchor="w", pady=(2, 0))
        elif res["cancelled"]:
            ttk.Label(frm, text="You cancelled the batch.", style="DialogSubtle.TLabel").pack(anchor="w")

        rows = [(j, "\u2716 Failed", m) for j, _k, m in res["failed"]]
        rows += [(j, "\u2014 Not attempted", r) for j, r in res["skipped"]]
        rows += [(j, "\u2714 Sent", "") for j in res["sent"]]
        tree_frame = ttk.Frame(frm, style="Dialog.TFrame")
        tree_frame.pack(fill="both", expand=True, pady=(10, 0))
        cols = ("row", "name", "email", "result", "detail")
        tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=14)
        for col, text, width in (("row", "Row", 50), ("name", "Recipient", 170), ("email", "Email", 210),
                                 ("result", "Result", 120), ("detail", "Detail", 380)):
            tree.heading(col, text=text)
            tree.column(col, width=width, anchor="w", stretch=col == "detail")
        tree.tag_configure("failed", background="#ffe3e3", foreground="#3a1414")
        tree.tag_configure("skipped", background="#ffe8cc", foreground="#4a2c00")
        tree.tag_configure("sent", background="#d3f9d8", foreground="#1a2e1a")
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        for j, result, detail in rows:
            tag = "failed" if "Failed" in result else ("sent" if "Sent" in result else "skipped")
            tree.insert("", "end", values=(j["row"], j["name"], j["email"], result, detail), tags=(tag,))

        btns = ttk.Frame(frm, style="Dialog.TFrame")
        btns.pack(fill="x", pady=(14, 0))
        retry = self._retry_jobs()

        def do_retry():
            dialog.destroy()
            if self._require_sender():
                subject, runs = self._send_subject
                self._start_send(retry, subject, runs)

        if retry:                                   # only offered when there is something to retry
            ttk.Button(btns, text=f"Retry failed & remaining ({len(retry)})", command=do_retry
                       ).pack(side="left", padx=(0, 6))

        def export():
            path = filedialog.asksaveasfilename(parent=dialog, defaultextension=".csv",
                                                initialfile="send_report.csv",
                                                filetypes=[("CSV file", "*.csv")])
            if not path:
                return
            try:
                with open(path, "w", newline="", encoding="utf-8-sig") as f:
                    w = csv.writer(f)
                    w.writerow(["Row", "Name", "Email", "Certificate file", "Result", "Detail"])
                    for j, result, detail in rows:
                        w.writerow([j["row"], j["name"], j["email"], os.path.basename(j.get("cert_path") or ""),
                                    result[2:], detail])
            except OSError as exc:
                messagebox.showerror("Export failed", str(exc), parent=dialog)

        ttk.Button(btns, text="Export report...", command=export).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="Close", command=dialog.destroy).pack(side="right")
        self._center_dialog(dialog, 900, 560)
