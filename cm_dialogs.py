"""Dialogs: Settings, first-run credentials prompt, How to Use, and the
hand-drawn title-bar icons. Mirrors Meraki's DialogsMixin patterns."""

import math
import re
import tkinter as tk
import webbrowser
from tkinter import ttk, messagebox

from PIL import Image, ImageDraw, ImageTk

from cm_constants import (
    APP_NAME, APP_ICON_PNG, GITHUB_ISSUES_URL, APP_PASSWORD_URL, THEMES,
    DAILY_LIMIT_FREE_GMAIL, DAILY_LIMIT_WORKSPACE,
)
from cm_mail import validate_smtp_credentials
from cm_compose import footer_label
from cm_utils import validate_email


def clean_app_password(raw):
    """Google shows app passwords in groups of 4 with spaces - drop all whitespace."""
    return re.sub(r"\s+", "", raw or "")


class DialogsMixin:
    # ---- icons ---------------------------------------------------------------
    def _make_gear_icon(self, size=32, color="#5b5fc7"):
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        cx = cy = size / 2
        outer_r, tooth_r, inner_r, teeth = size * 0.34, size * 0.46, size * 0.16, 8
        pts = []
        for i in range(teeth * 2):
            a = i * math.pi / teeth
            r = tooth_r if i % 2 == 0 else outer_r
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        draw.polygon(pts, fill=color)
        draw.ellipse((cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r), fill=(0, 0, 0, 0))
        return ImageTk.PhotoImage(img)

    def _set_dialog_icon(self, dialog, kind="app"):
        try:
            if kind == "gear":
                self._dlg_icon_img = self._make_gear_icon(32, self._current_theme_colors["accent"])
            else:
                from cm_core import load_app_logo
                self._dlg_icon_img = ImageTk.PhotoImage(load_app_logo(32))
            dialog.iconphoto(False, self._dlg_icon_img)
        except Exception:
            pass

    # ---- shared credentials form ------------------------------------------------
    def _build_credentials_block(self, parent, email_v, pw_v, name_v, width=38):
        """Sender address, app password (+show), display name, help link and a
        Test connection button. Returns (status_label, set_enabled)."""
        theme = self._current_theme_colors
        ttk.Label(parent, text="Gmail address (sender)", font=("Segoe UI", 10, "bold"),
                  style="Dialog.TLabel").pack(anchor="w")
        email_entry = ttk.Entry(parent, textvariable=email_v, width=width)
        email_entry.pack(fill="x", pady=(4, 10))

        ttk.Label(parent, text="App password", font=("Segoe UI", 10, "bold"),
                  style="Dialog.TLabel").pack(anchor="w")
        pw_entry = ttk.Entry(parent, textvariable=pw_v, width=width, show="\u2022")
        pw_entry.pack(fill="x", pady=(4, 2))
        show_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(parent, text="Show password", variable=show_var, style="Dialog.TCheckbutton",
                        command=lambda: pw_entry.config(show="" if show_var.get() else "\u2022")
                        ).pack(anchor="w")
        link = ttk.Label(parent, text="How to create a Gmail app password \u2192", foreground=theme["accent"],
                         style="Dialog.TLabel", cursor="hand2")
        link.pack(anchor="w", pady=(4, 0))
        link.bind("<Button-1>", lambda e: webbrowser.open(APP_PASSWORD_URL))
        ttk.Label(parent, style="DialogSubtle.TLabel", wraplength=340, justify="left",
                  text="Needs 2-Step Verification turned on for that Gmail account. Use the 16-letter "
                       "app password, not your normal password.").pack(anchor="w", pady=(2, 10))

        ttk.Label(parent, text="Sender name (optional)", font=("Segoe UI", 10, "bold"),
                  style="Dialog.TLabel").pack(anchor="w")
        ttk.Entry(parent, textvariable=name_v, width=width).pack(fill="x", pady=(4, 10))

        row = ttk.Frame(parent, style="Dialog.TFrame")
        row.pack(fill="x")
        test_btn = ttk.Button(row, text="Test connection")
        test_btn.pack(side="left")
        status = ttk.Label(parent, text="", style="DialogSubtle.TLabel", wraplength=340, justify="left")
        status.pack(anchor="w", pady=(8, 0))

        def show(message, color=None):
            status.config(text=message, foreground=color or theme["subtle_text"])

        def on_test():
            ok, addr, reason = validate_email(email_v.get())
            pw = clean_app_password(pw_v.get())
            if not ok or not pw:
                show("Enter a valid Gmail address and the app password first.", "#e03131")
                return
            test_btn.config(state="disabled")
            show("Signing in to Gmail...")

            def done(result):
                if not test_btn.winfo_exists():
                    return
                test_btn.config(state="normal")
                status_kind, payload = result
                if status_kind == "valid":
                    show("\u2714 Connected - these credentials work.", "#2f9e44")
                elif status_kind == "invalid":
                    show(f"Gmail rejected these credentials: {payload}", "#e03131")
                else:
                    show(f"Couldn't check right now ({payload}). Check your internet connection.", "#e03131")

            self._run_async(lambda: validate_smtp_credentials(addr, pw), done)

        test_btn.config(command=on_test)
        email_entry.focus_set()
        return show, test_btn, on_test

    # ---- Settings ------------------------------------------------------------------
    def _open_settings_dialog(self):
        original_theme = self.theme.get()
        dialog = self._new_dialog("Settings")
        self._set_dialog_icon(dialog, "gear")

        email_v = tk.StringVar(value=self.sender_email.get())
        pw_v = tk.StringVar(value=self.sender_password)
        name_v = tk.StringVar(value=self.sender_name.get())
        delay_v = tk.StringVar(value=str(self.send_delay.get()))

        outer = ttk.Frame(dialog, padding=18, style="Dialog.TFrame")
        outer.pack(fill="both", expand=True)
        left = ttk.Frame(outer, style="Dialog.TFrame")
        left.grid(row=0, column=0, sticky="n", padx=(0, 22))
        right = ttk.Frame(outer, style="Dialog.TFrame")
        right.grid(row=0, column=1, sticky="n")

        ttk.Label(left, text="Sender account", font=("Segoe UI", 12, "bold"),
                  style="Dialog.TLabel").pack(anchor="w", pady=(0, 8))
        self._build_credentials_block(left, email_v, pw_v, name_v)

        # ---- footer: just a bar that opens the Footer tab ----
        theme = self._current_theme_colors
        ttk.Label(right, text="Email footer", font=("Segoe UI", 12, "bold"),
                  style="Dialog.TLabel").pack(anchor="w", pady=(0, 6))
        bar = tk.Frame(right, bg=theme["tab_inactive_bg"], highlightthickness=1,
                       highlightbackground=theme["tab_border"], cursor="hand2")
        bar.pack(fill="x")
        n = len(self.footers)
        active = (footer_label(self.active_footer, self.footers[self.active_footer])
                  if 0 <= self.active_footer < n else "none")
        title = tk.Label(bar, text="\u270e  Edit default footer\u2026", bg=theme["tab_inactive_bg"], fg=theme["text"],
                         font=("Segoe UI", 10, "bold"), anchor="w", padx=10)
        title.pack(fill="x", pady=(8, 0))
        info = tk.Label(bar, text=f"{n} saved footer(s)  \u00b7  in use: {active}", bg=theme["tab_inactive_bg"],
                        fg=theme["subtle_text"], font=("Segoe UI", 8), anchor="w", padx=10)
        info.pack(fill="x", pady=(0, 8))
        ttk.Label(right, style="DialogSubtle.TLabel", wraplength=430, justify="left",
                  text="Opens the Footer tab (your other settings here are saved first).").pack(anchor="w", pady=(4, 0))

        ttk.Separator(right).pack(fill="x", pady=(14, 10))
        row = ttk.Frame(right, style="Dialog.TFrame")
        row.pack(fill="x")
        ttk.Label(row, text="Theme", font=("Segoe UI", 10, "bold"), style="Dialog.TLabel").pack(side="left")
        theme_combo = ttk.Combobox(row, textvariable=self.theme, state="readonly", width=14,
                                   values=list(THEMES.keys()))
        theme_combo.pack(side="left", padx=(8, 22))
        theme_combo.bind("<<ComboboxSelected>>", lambda e: self._apply_theme(self.theme.get()))
        ttk.Label(row, text="Pause between emails (s)", font=("Segoe UI", 10, "bold"),
                  style="Dialog.TLabel").pack(side="left")
        ttk.Spinbox(row, from_=0, to=30, increment=0.5, textvariable=delay_v, width=5).pack(side="left", padx=(8, 0))
        ttk.Label(right, style="DialogSubtle.TLabel", wraplength=430, justify="left",
                  text=f"Gmail allows roughly {DAILY_LIMIT_FREE_GMAIL} recipients per rolling 24 hours on a free "
                       f"account ({DAILY_LIMIT_WORKSPACE:,} on Google Workspace). A short pause between "
                       f"emails keeps sending steady.").pack(anchor="w", pady=(6, 0))

        def clear_history():
            count = len(self.sent_log.entries)
            if not count:
                messagebox.showinfo("Sent history", "The sent history is already empty.", parent=dialog)
                return
            if messagebox.askyesno("Clear sent history",
                                   f"Forget all {count} sent record(s)? Everyone will become eligible "
                                   f"to receive their certificate again.", parent=dialog):
                self.sent_log.clear()
                if self.csv_rows:
                    self._recompute_analysis()

        ttk.Button(right, text="Clear sent history...", command=clear_history).pack(anchor="w", pady=(10, 0))

        btn_row = ttk.Frame(outer, style="Dialog.TFrame")
        btn_row.grid(row=1, column=0, columnspan=2, sticky="w", pady=(18, 0))

        def do_save():
            ok, addr, _reason = validate_email(email_v.get())
            pw = clean_app_password(pw_v.get())
            if email_v.get().strip() and not ok:
                messagebox.showerror("Settings", "That Gmail address doesn't look valid.", parent=dialog)
                return False
            if pw and not ok:
                messagebox.showerror("Settings", "Enter the Gmail address that the app password belongs to.",
                                     parent=dialog)
                return False
            try:
                delay = max(0.0, min(30.0, float(delay_v.get())))
            except ValueError:
                messagebox.showerror("Settings", "The pause between emails must be a number of seconds.",
                                     parent=dialog)
                return False
            self.sender_email.set(addr if ok else "")
            self.sender_password = pw
            self.sender_name.set(name_v.get().strip())
            self.send_delay.set(delay)
            self._save_settings()
            self._update_sender_status()
            return True

        def on_save():
            if do_save():
                dialog.destroy()

        def edit_footers(_event=None):
            if do_save():
                dialog.destroy()
                self.after(50, self._open_footer_tab)

        for w in (bar, title, info):
            w.bind("<Button-1>", edit_footers)

        def on_cancel():
            self._apply_theme(original_theme)
            dialog.destroy()

        ttk.Button(btn_row, text="Save", command=on_save).pack(side="left", padx=(0, 6))
        ttk.Button(btn_row, text="Cancel", command=on_cancel).pack(side="left")
        dialog.protocol("WM_DELETE_WINDOW", on_cancel)
        self._center_dialog(dialog)

    # ---- first-run credentials prompt ---------------------------------------------------
    def _maybe_show_credentials_prompt(self):
        """Shown at launch whenever no sender account is on file (skippable)."""
        if not self.credentials_ready():
            self._show_credentials_prompt_dialog()

    def _show_credentials_prompt_dialog(self):
        dialog = self._new_dialog("Set up your sender account")
        self._set_dialog_icon(dialog)
        email_v = tk.StringVar(value=self.sender_email.get())
        pw_v = tk.StringVar(value=self.sender_password)
        name_v = tk.StringVar(value=self.sender_name.get())

        frm = ttk.Frame(dialog, padding=18, style="Dialog.TFrame")
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="Set up the Gmail account to send from", font=("Segoe UI", 12, "bold"),
                  style="Dialog.TLabel").pack(anchor="w")
        ttk.Label(frm, wraplength=380, justify="left", style="Dialog.TLabel",
                  text=f"{APP_NAME} sends each certificate through your Gmail account using an app "
                       f"password. You can skip this and explore the app - sending needs it, and you "
                       f"can set it any time from Settings.").pack(anchor="w", pady=(8, 14))
        show, test_btn, _on_test = self._build_credentials_block(frm, email_v, pw_v, name_v)

        btn_row = ttk.Frame(frm, style="Dialog.TFrame")
        btn_row.pack(fill="x", pady=(16, 0))
        save_btn = ttk.Button(btn_row, text="Save & Continue")
        save_btn.pack(side="left", padx=(0, 6))
        skip_btn = ttk.Button(btn_row, text="Skip for now", command=dialog.destroy)
        skip_btn.pack(side="left")

        def on_save():
            ok, addr, _r = validate_email(email_v.get())
            pw = clean_app_password(pw_v.get())
            if not ok or not pw:
                show("Enter a valid Gmail address and the app password.", "#e03131")
                return
            save_btn.config(state="disabled")
            skip_btn.config(state="disabled")
            show("Checking with Gmail...")

            def done(result):
                if not dialog.winfo_exists():
                    return
                save_btn.config(state="normal")
                skip_btn.config(state="normal")
                kind, payload = result
                if kind == "valid":
                    self.sender_email.set(addr)
                    self.sender_password = pw
                    self.sender_name.set(name_v.get().strip())
                    self._save_settings()
                    self._update_sender_status()
                    dialog.destroy()
                elif kind == "invalid":
                    show(f"Gmail rejected these credentials: {payload}", "#e03131")
                else:
                    show(f"Couldn't check right now ({payload}). Check your internet connection, "
                         f"or skip and set it up later.", "#e03131")

            self._run_async(lambda: validate_smtp_credentials(addr, pw), done)

        save_btn.config(command=on_save)
        dialog.bind("<Return>", lambda e: on_save())
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        self._center_dialog(dialog)

    # ---- How to use / help ----------------------------------------------------------------
    def _open_github_issues(self):
        webbrowser.open_new_tab(GITHUB_ISSUES_URL)

    def _how_to_use_content(self):
        return [
            ("h1", "What this app does"),
            ("body", f"{APP_NAME} emails each person their certificate. It reads the same CSV/Excel file you "
                     "gave Meraki, finds each person's generated certificate file, and sends it through Gmail."),
            ("h1", "Step by step"),
            ("bullet", "\u2022 Upload the source file. Pick the column with names and the column with email addresses."),
            ("bullet", "\u2022 Choose the folder where Meraki saved the certificates. The app checks every row "
                       "and tells you which certificates are missing and which emails are invalid."),
            ("bullet", "\u2022 In the Recipients tab, choose which rows to send to (All rows, or a custom range "
                       "like \"2-5, 8, 10-12\"; shift/ctrl-click and Lock work exactly like in Meraki)."),
            ("bullet", "\u2022 In the Compose tab, write the subject and message. Click Insert name (or type "
                       "{name}) to put each person's name in. Your footer is added automatically."),
            ("bullet", "\u2022 Click \"Send test to myself\" first, then \"Send certificates\"."),
            ("h1", "Reading the grid"),
            ("bullet", "\u2022 Green: will be sent.   Amber: selected but will be skipped (see the Status column "
                       "for why).   Red: not selected."),
            ("h1", "Avoiding duplicate emails"),
            ("body", "Every successful send is remembered by Certificate ID. Next time, people who already "
                     "received their certificate show \u2714 Sent and are skipped automatically. Tick "
                     "\"Include already-sent rows\" if you really want to resend. If you correct someone's "
                     "email address, they count as not sent yet."),
            ("h1", "Gmail sender account"),
            ("body", "Gmail needs an app password (turn on 2-Step Verification, then create one at "
                     "myaccount.google.com/apppasswords). It is stored encrypted for your Windows user. "
                     f"Free Gmail accounts allow about {DAILY_LIMIT_FREE_GMAIL} recipients per rolling 24 hours."),
            ("h1", "The footer"),
            ("body", "Edit your reusable footer (bold, italic, underline, sizes, links) in Settings. It is "
                     "saved and added under every message."),
            ("h1", "If something fails"),
            ("body", "When a send finishes you get a summary of who succeeded and who didn't, with the reason. "
                     "You can retry the failed ones or export the report."),
        ]

    def _open_how_to_use_dialog(self):
        theme = self._current_theme_colors
        dialog = self._new_dialog(f"How to Use {APP_NAME}", resizable=True)
        self._set_dialog_icon(dialog)
        frm = ttk.Frame(dialog, padding=16, style="Dialog.TFrame")
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text=f"How to Use {APP_NAME}", font=("Segoe UI", 16, "bold"),
                  style="Dialog.TLabel").pack(anchor="w", pady=(0, 12))
        text_frame = ttk.Frame(frm, style="Dialog.TFrame")
        text_frame.pack(fill="both", expand=True)
        tw = tk.Text(text_frame, wrap="word", relief="flat", padx=14, pady=10, bg=theme["dialog_bg"],
                     fg=theme["text"], font=("Segoe UI", 10), highlightthickness=0, borderwidth=0, cursor="arrow")
        vsb = ttk.Scrollbar(text_frame, orient="vertical", command=tw.yview)
        tw.configure(yscrollcommand=vsb.set)
        tw.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        tw.tag_configure("h1", font=("Segoe UI", 13, "bold"), foreground=theme["accent2"], spacing1=14, spacing3=6)
        tw.tag_configure("body", font=("Segoe UI", 10), spacing3=4)
        tw.tag_configure("bullet", font=("Segoe UI", 10), lmargin1=18, lmargin2=30, spacing3=2)
        for kind, text in self._how_to_use_content():
            tw.insert("end", text + "\n", kind)
        tw.configure(state="disabled")
        ttk.Button(frm, text="Close", command=dialog.destroy).pack(anchor="e", pady=(12, 0))
        self._center_dialog(dialog, 760, 620)
