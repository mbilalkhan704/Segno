"""Core mixin: app init/state, splash screen, settings persistence, recent
files, and a small thread helper. Ported from Meraki's mck_core."""

import json
import math
import os
import queue
import re
import sys
import threading
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageDraw, ImageTk

from cm_constants import (
    SETTINGS_PATH, SENT_LOG_PATH, APP_ICON_PNG, APP_ICON_ICO, ORIC_LOGO_FILE, APP_FULL_TITLE,
    SPLASH_BG, SPLASH_PALETTE, SPLASH_DURATION_MS, SPLASH_LOGO_SIZE, SPLASH_CREDIT_TEXT,
    THEMES, DEFAULT_THEME, DEFAULT_SEND_DELAY, MAX_RECENT_FILES, MAX_REMEMBERED_FOLDERS,
)
from cm_richtext import normalize_runs
from cm_sentlog import SentLog
from cm_utils import atomic_write_json, protect_secret, unprotect_secret


def draw_envelope_icon(size=256, body="#5b5fc7", accent="#ff8a5b"):
    """Placeholder app logo (used when icons/app_icon.png is missing)."""
    s = size * 2
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    m = s * 0.12
    top, bot = s * 0.26, s * 0.76
    d.rounded_rectangle((m, top, s - m, bot), radius=s * 0.05, fill=body)
    d.line((m, top, s / 2, s * 0.56, s - m, top), fill="#ffffff", width=int(s * 0.035), joint="curve")
    d.ellipse((s * 0.66, s * 0.14, s * 0.90, s * 0.38), fill=accent, outline="#ffffff", width=int(s * 0.02))
    d.line((s * 0.725, s * 0.265, s * 0.765, s * 0.31, s * 0.84, s * 0.215), fill="#ffffff",
           width=int(s * 0.025), joint="curve")
    return img.resize((size, size), Image.LANCZOS)


def load_app_logo(max_dim=256):
    if os.path.isfile(APP_ICON_PNG):
        try:
            img = Image.open(APP_ICON_PNG).convert("RGBA")
            img.thumbnail((max_dim, max_dim), Image.LANCZOS)
            return img
        except Exception:
            pass
    return draw_envelope_icon(max_dim)


class CoreMixin:
    def __init__(self):
        super().__init__()
        self.withdraw()                       # hide the blank root immediately
        self.title(APP_FULL_TITLE)
        self._set_window_icon()
        self.minsize(1150, 660)

        # ---- source / analysis state ----------------------------------------
        self.csv_path = None
        self.csv_headers = []
        self.csv_rows = []
        self.name_col = tk.StringVar()
        self.email_col = tk.StringVar()
        self.cert_folder = None
        self.cert_index = None
        self.row_infos = []                   # analysis, one RowInfo per row
        self.row_send_state = {}              # row -> (state, detail) for this session
        self.include_sent = tk.BooleanVar(value=False)
        self.subject_var = tk.StringVar()
        self._problem_cursor = 0

        # ---- row selection (same attributes Meraki's source view expects) ------
        self.row_selection_mode = tk.StringVar(value="all")
        self.row_selection_text = tk.StringVar(value="")
        self.row_selection_locked_chips = []
        self._row_selection_syncing = False
        self.current_view = "recipients"

        # ---- settings -------------------------------------------------------------
        self.sender_email = tk.StringVar()
        self.sender_name = tk.StringVar()
        self.sender_password = ""
        self.send_delay = tk.DoubleVar(value=DEFAULT_SEND_DELAY)
        self.footers = []                     # saved footers: a list of rich-text run lists
        self.active_footer = -1               # index of the footer added to emails (-1 = none)
        self._footer_tab_open = False
        self._fv_index = 0
        self._fv_new = False
        self._fv_baseline = []
        self._view_before_footer = "recipients"
        self.theme = tk.StringVar(value=DEFAULT_THEME)
        self._current_theme_colors = THEMES[DEFAULT_THEME]
        self.recent_files = []
        self.cert_folders = {}                # source path -> certificates folder
        self.sent_log = SentLog(SENT_LOG_PATH)

        # ---- runtime ---------------------------------------------------------------
        self._toggle_redraws = []
        self._active_modal_dialogs = []
        self._rich_editors = []
        self._modal_focus_poll_running = False
        self._sending = False
        self._cancel_event = threading.Event()
        self._send_queue = None
        self._last_results = {}

        self.protocol("WM_DELETE_WINDOW", self._on_close_request)
        self._show_splash()
        self._load_settings()
        self._build_ui()
        self._apply_theme(self.theme.get())
        self._update_sender_status()

    def _set_window_icon(self):
        try:
            if os.path.isfile(APP_ICON_ICO) and sys.platform.startswith("win"):
                self.iconbitmap(APP_ICON_ICO)
            else:
                self._window_icon = ImageTk.PhotoImage(load_app_logo(64))
                self.iconphoto(True, self._window_icon)
        except Exception:
            pass

    # ---- threads -------------------------------------------------------------------
    def _run_async(self, fn, on_done):
        """Run fn() on a worker thread; on_done(result) runs on the Tk thread.
        Uses a queue polled by after() - never touches Tk from the worker."""
        q = queue.Queue()

        def work():
            try:
                q.put(("ok", fn()))
            except Exception as exc:  # noqa: BLE001
                q.put(("err", exc))

        def poll():
            try:
                kind, value = q.get_nowait()
            except queue.Empty:
                self.after(80, poll)
                return
            on_done(value if kind == "ok" else ("error", str(value)))

        threading.Thread(target=work, daemon=True).start()
        self.after(80, poll)

    # ---- splash ----------------------------------------------------------------------
    def _show_splash(self):
        splash = tk.Toplevel(self)
        splash.overrideredirect(True)
        w, h = 720, 500
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        splash.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")
        splash.configure(bg=SPLASH_BG)
        canvas = tk.Canvas(splash, width=w, height=h, highlightthickness=0, bg=SPLASH_BG)
        canvas.pack(fill="both", expand=True)

        def flatten(img):
            img = img.convert("RGBA")
            ratio = min(SPLASH_LOGO_SIZE / img.width, SPLASH_LOGO_SIZE / img.height, 1.0)
            img = img.resize((max(1, int(img.width * ratio)), max(1, int(img.height * ratio))), Image.LANCZOS)
            backing = Image.new("RGBA", img.size, SPLASH_BG)
            backing.paste(img, (0, 0), img)
            return ImageTk.PhotoImage(backing)

        oric = None
        if os.path.isfile(ORIC_LOGO_FILE):
            try:
                oric = flatten(Image.open(ORIC_LOGO_FILE))
            except Exception:
                oric = None
        self._splash, self._splash_canvas = splash, canvas
        self._splash_app_logo_img = flatten(load_app_logo(SPLASH_LOGO_SIZE * 2))
        self._splash_oric_logo_img = oric
        self._splash_frame_i, self._splash_w, self._splash_h = 0, w, h
        splash.bind("<Button-1>", lambda e: self._finish_splash())
        self._splash_after_id = self.after(SPLASH_DURATION_MS, self._finish_splash)
        self._animate_splash()

    def _animate_splash(self):
        canvas = getattr(self, "_splash_canvas", None)
        if canvas is None or not canvas.winfo_exists():
            return
        w, h = self._splash_w, self._splash_h
        cx, cy = w / 2, h / 2 - 60
        t = self._splash_frame_i / 30.0
        canvas.delete("anim")
        for i in range(16):                                   # sunburst
            a = t * 0.12 + i * (2 * math.pi / 16)
            canvas.create_line(cx + 65 * math.cos(a), cy + 65 * math.sin(a) * 0.6,
                               cx + 210 * math.cos(a), cy + 210 * math.sin(a) * 0.6,
                               fill=SPLASH_PALETTE[i % len(SPLASH_PALETTE)], width=1, tags="anim")
        pts = [(cx + 160 * math.sin(2 * (t + k * 0.02)), cy + 75 * math.sin(3 * (t + k * 0.02) + 1.0))
               for k in range(0, 200, 4)]                     # Lissajous ribbon
        for i in range(len(pts) - 1):
            canvas.create_line(*pts[i], *pts[i + 1], fill=SPLASH_PALETTE[i % len(SPLASH_PALETTE)],
                               width=2, capstyle="round", tags="anim")
        for i, color in enumerate(SPLASH_PALETTE):            # orbiting dots
            ang = t * (0.55 + i * 0.13) + i * (math.pi / 3)
            r_ = 100 + i * 15
            x, y, r = cx + r_ * math.cos(ang), cy + r_ * math.sin(ang) * 0.6, 4 + (i % 3)
            canvas.create_oval(x - r, y - r, x + r, y + r, fill=color, outline="", tags="anim")
        imgs = [i for i in (self._splash_app_logo_img, self._splash_oric_logo_img) if i is not None]
        gap = 26
        total = sum(i.width() for i in imgs) + gap * (len(imgs) - 1)
        x = cx - total / 2
        for img in imgs:
            canvas.create_image(x + img.width() / 2, cy, image=img, tags="anim")
            x += img.width() + gap
        canvas.create_text(cx, cy + 145, text=SPLASH_CREDIT_TEXT, fill="#e8e8f0",
                           font=("Segoe UI", 10), tags="anim", width=w - 70, justify="center")
        sy, sr = cy + 195, 15
        canvas.create_arc(cx - sr, sy - sr, cx + sr, sy + sr, start=(t * 220) % 360, extent=270,
                          style="arc", outline="#ffffff", width=3, tags="anim")
        dots = "." * (1 + (self._splash_frame_i // 15) % 3)
        canvas.create_text(cx, sy + sr + 22, text=f"Initializing{dots}", fill="#a9a9c0",
                           font=("Segoe UI", 9), tags="anim")
        self._splash_frame_i += 1
        self._splash_anim_id = self.after(33, self._animate_splash)

    def _finish_splash(self):
        if getattr(self, "_splash_done", False):
            return
        self._splash_done = True
        for attr in ("_splash_after_id", "_splash_anim_id"):
            after_id = getattr(self, attr, None)
            if after_id is not None:
                try:
                    self.after_cancel(after_id)
                except Exception:
                    pass
        splash = getattr(self, "_splash", None)
        if splash is not None and splash.winfo_exists():
            splash.destroy()
        self.deiconify()
        self._maximize_window()
        self._install_close_hook()
        self._maybe_show_credentials_prompt()

    # ---- settings -----------------------------------------------------------------------
    def _load_settings(self):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
        self.sender_email.set((data.get("sender_email") or "").strip())
        self.sender_name.set((data.get("sender_name") or "").strip())
        self.sender_password = unprotect_secret(data.get("sender_password_enc") or "")
        name = data.get("theme")
        if name in THEMES:
            self.theme.set(name)
            self._current_theme_colors = THEMES[name]
        try:
            self.send_delay.set(max(0.0, min(30.0, float(data.get("send_delay", DEFAULT_SEND_DELAY)))))
        except (TypeError, ValueError):
            self.send_delay.set(DEFAULT_SEND_DELAY)
        def clean(runs):
            return normalize_runs([r for r in runs if isinstance(r, dict) and "text" in r]) \
                if isinstance(runs, list) else []

        footers = data.get("footers")
        if isinstance(footers, list):
            self.footers = [f for f in (clean(x) for x in footers) if f]
        else:                                  # older single-footer settings file
            legacy = clean(data.get("footer_runs"))
            self.footers = [legacy] if legacy else []
        try:
            active = int(data.get("active_footer", 0 if self.footers else -1))
        except (TypeError, ValueError):
            active = -1
        self.active_footer = active if 0 <= active < len(self.footers) else -1
        rf = data.get("recent_files")
        if isinstance(rf, list):
            self.recent_files = [p for p in rf if isinstance(p, str)][-MAX_RECENT_FILES:]
        cf = data.get("cert_folders")
        if isinstance(cf, dict):
            self.cert_folders = {k: v for k, v in cf.items() if isinstance(k, str) and isinstance(v, str)}

    def _save_settings(self):
        try:
            atomic_write_json(SETTINGS_PATH, {
                "sender_email": self.sender_email.get().strip(),
                "sender_name": self.sender_name.get().strip(),
                "sender_password_enc": protect_secret(self.sender_password),
                "theme": self.theme.get(),
                "send_delay": self.send_delay.get(),
                "footers": self.footers,
                "active_footer": self.active_footer,
                "recent_files": self.recent_files,
                "cert_folders": self.cert_folders,
            })
        except Exception:
            pass

    def _record_recent_file(self, path):
        """Newest last, capped, oldest dropped first (Meraki's convention)."""
        path = os.path.abspath(path)
        self.recent_files = [p for p in self.recent_files if os.path.abspath(p) != path]
        self.recent_files.append(path)
        self.recent_files = self.recent_files[-MAX_RECENT_FILES:]
        self._save_settings()
        if hasattr(self, "recent_files_frame"):
            self._refresh_recent_files_list()

    def _remember_cert_folder(self, folder):
        if not self.csv_path:
            return
        self.cert_folders.pop(self.csv_path, None)
        self.cert_folders[self.csv_path] = folder
        while len(self.cert_folders) > MAX_REMEMBERED_FOLDERS:
            self.cert_folders.pop(next(iter(self.cert_folders)))
        self._save_settings()

    def _active_footer_runs(self):
        return self.footers[self.active_footer] if 0 <= self.active_footer < len(self.footers) else []

    def credentials_ready(self):
        return bool(self.sender_email.get().strip() and self.sender_password)
