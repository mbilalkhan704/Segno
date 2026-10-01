"""Builds the main window: toolbar, credit footer, scrollable left panel
(numbered sections), the Recipients / Compose tab container, and the
upload gate screen that sits on top until a source file is loaded."""

import tkinter as tk
from tkinter import ttk

from PIL import ImageTk

from cm_constants import APP_NAME, APP_SUBTITLE, APP_CREDIT_TEXT
from cm_core import load_app_logo


class BuildUiMixin:
    def _build_ui(self):
        theme = self._current_theme_colors

        # ---- toolbar -------------------------------------------------------------
        self.toolbar = tk.Frame(self, bg=theme["toolbar_bg"], height=52)
        self.toolbar.pack(side="top", fill="x")
        self.title_frame = tk.Frame(self.toolbar, bg=theme["toolbar_bg"])
        self.title_frame.pack(side="left", padx=18, pady=10)
        self.toolbar_icon_label = None
        try:
            self._toolbar_icon_img = ImageTk.PhotoImage(load_app_logo(48))
            self.toolbar_icon_label = tk.Label(self.title_frame, image=self._toolbar_icon_img, bg=theme["toolbar_bg"])
            self.toolbar_icon_label.pack(side="left", padx=(0, 8))
        except Exception:
            self.toolbar_icon_label = None
        self.brand_label = tk.Label(self.title_frame, text=APP_NAME.upper(), bg=theme["toolbar_bg"],
                                    fg=theme["toolbar_fg"], font=("Segoe UI Black", 16))
        self.brand_label.pack(side="left")
        self.sub_label = tk.Label(self.title_frame, text=f" \u2502 {APP_SUBTITLE}", bg=theme["toolbar_bg"],
                                  fg=theme.get("toolbar_sub", theme["toolbar_fg"]), font=("Segoe UI Semibold", 10))
        self.sub_label.pack(side="left", padx=(4, 0), pady=(2, 0))

        self.settings_btn = tk.Button(self.toolbar, text="\u2699 Settings", relief="flat", bd=0, padx=16, pady=8,
                                      cursor="hand2", font=("Segoe UI", 11, "bold"),
                                      command=self._open_settings_dialog)
        self.settings_btn.pack(side="right", padx=18, pady=10)
        self.issues_btn = tk.Button(self.toolbar, text="\u2753 Help", relief="flat", bd=0, padx=14, pady=6,
                                    cursor="hand2", font=("Segoe UI", 10, "bold"), command=self._open_github_issues)
        self.issues_btn.pack(side="right", padx=(0, 4), pady=10)
        self.how_to_use_btn = tk.Button(self.toolbar, text="\U0001F4D6 How to Use", relief="flat", bd=0, padx=14,
                                        pady=6, cursor="hand2", font=("Segoe UI", 10, "bold"),
                                        command=self._open_how_to_use_dialog)
        self.how_to_use_btn.pack(side="right", padx=(0, 4), pady=10)

        # ---- credit footer ----------------------------------------------------------
        self.footer_bar = tk.Frame(self, height=26)
        self.footer_bar.pack(side="bottom", fill="x")
        self.footer_note = tk.Label(self.footer_bar, text=APP_CREDIT_TEXT, font=("Segoe UI", 12, "italic"))
        self.footer_note.pack(side="right", padx=14, pady=4)

        self.main_root_frame = ttk.Frame(self, padding=10)      # packed by _reveal_main_ui
        root = self.main_root_frame

        # ---- scrollable left panel -------------------------------------------------------
        left_container = ttk.Frame(root, width=400)
        left_container.pack(side="left", fill="y", padx=(0, 10))
        left_container.pack_propagate(False)
        self.left_canvas = tk.Canvas(left_container, highlightthickness=0, bd=0)
        left_scrollbar = ttk.Scrollbar(left_container, orient="vertical", command=self.left_canvas.yview)
        scroll_frame = ttk.Frame(self.left_canvas)
        scroll_frame.bind("<Configure>", lambda e: self.left_canvas.configure(scrollregion=self.left_canvas.bbox("all")))
        self._left_window = self.left_canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        self.left_canvas.bind("<Configure>", lambda e: self.left_canvas.itemconfig(self._left_window, width=e.width))
        self.left_canvas.configure(yscrollcommand=left_scrollbar.set)
        self.left_canvas.pack(side="left", fill="both", expand=True)
        left_scrollbar.pack(side="right", fill="y")
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.bind_all(seq, self._on_left_panel_mousewheel, add="+")
        left = scroll_frame
        right = ttk.Frame(root)
        right.pack(side="left", fill="both", expand=True)

        # ---- 1. Source file -----------------------------------------------------------------
        box = self._section(left, "1. Source file")
        ttk.Button(box, text="Change source file...", command=self._upload_data_file).pack(fill="x")
        self.csv_label = ttk.Label(box, text="No file selected", style="Subtle.TLabel", wraplength=340)
        self.csv_label.pack(fill="x", pady=(4, 8))
        ttk.Label(box, text="Column with the name:").pack(anchor="w")
        self.name_combo = ttk.Combobox(box, textvariable=self.name_col, state="readonly")
        self.name_combo.pack(fill="x", pady=(2, 8))
        self.name_combo.bind("<<ComboboxSelected>>", lambda e: self._on_columns_changed())
        ttk.Label(box, text="Column with the email address:").pack(anchor="w")
        self.email_combo = ttk.Combobox(box, textvariable=self.email_col, state="readonly")
        self.email_combo.pack(fill="x", pady=(2, 4))
        self.email_combo.bind("<<ComboboxSelected>>", lambda e: self._on_columns_changed())
        self.email_summary_label = ttk.Label(box, text="", style="Subtle.TLabel", wraplength=340, justify="left")
        self.email_summary_label.pack(anchor="w", pady=(4, 0))

        # ---- 2. Certificates folder ---------------------------------------------------------------
        box = self._section(left, "2. Certificates folder")
        ttk.Button(box, text="Choose certificates folder...", command=self._choose_cert_folder).pack(fill="x")
        self.cert_folder_label = ttk.Label(box, text="No folder selected", style="Subtle.TLabel", wraplength=340)
        self.cert_folder_label.pack(fill="x", pady=(4, 6))
        self.cert_summary_label = ttk.Label(box, text="", style="Subtle.TLabel", wraplength=340, justify="left")
        self.cert_summary_label.pack(anchor="w")
        row = ttk.Frame(box)
        row.pack(fill="x", pady=(8, 0))
        ttk.Button(row, text="Re-scan folder", command=self._rescan_cert_folder).pack(side="left")
        ttk.Button(row, text="Next problem row \u25b8", command=self._next_problem_row).pack(side="left", padx=(6, 0))
        ttk.Label(box, style="Subtle.TLabel", wraplength=340, justify="left",
                  text="Files are matched the way Meraki names them: Name_CertificateID "
                       "(.pdf, .png, .jpg).").pack(anchor="w", pady=(8, 0))

        # ---- 3. Sending -----------------------------------------------------------------------------
        box = self._section(left, "3. Send")
        self.sender_status_label = ttk.Label(box, text="", style="Subtle.TLabel", wraplength=340,
                                             justify="left", cursor="hand2")
        self.sender_status_label.pack(anchor="w", pady=(0, 8))
        self.sender_status_label.bind("<Button-1>", lambda e: self._open_settings_dialog())
        self._make_toggle(box, "Include already-sent rows", self.include_sent,
                          on_toggle=self._recompute_analysis).pack(anchor="w", pady=(0, 6))
        self.send_summary_label = ttk.Label(box, text="", style="Subtle.TLabel", wraplength=340, justify="left")
        self.send_summary_label.pack(anchor="w", pady=(0, 8))
        self.test_btn = ttk.Button(box, text="Send test to myself", command=self._on_test_send_clicked)
        self.test_btn.pack(fill="x", pady=(0, 6))
        self.send_btn = ttk.Button(box, text="Send certificates", command=self._on_send_clicked)
        self.send_btn.pack(fill="x", pady=(0, 6))
        # Only shown while a send is actually running (like Meraki's progress bar).
        self.cancel_btn = ttk.Button(box, text="Cancel sending", style="Danger.TButton", command=self._cancel_send)
        self.send_progress = ttk.Progressbar(box, mode="determinate")
        self.send_status_label = ttk.Label(box, text="", style="Subtle.TLabel", wraplength=340, justify="left")
        self.send_status_label.pack(fill="x", pady=(4, 6))

        # ---- Recipients / Compose tabs ----------------------------------------------------------------
        self.view_tabs_bar = tk.Frame(right, bg=theme["bg"])
        self.view_tabs_bar.pack(side="top", fill="x", pady=(0, 4))
        self.view_container = ttk.Frame(right)
        self.view_container.pack(fill="both", expand=True)
        self.recipients_view_frame = ttk.Frame(self.view_container)
        self._build_recipients_view(self.recipients_view_frame)
        self.compose_view_frame = ttk.Frame(self.view_container)
        self._build_compose_view(self.compose_view_frame)
        self.footer_view_frame = ttk.Frame(self.view_container)     # shown only while the Footer tab is open
        self._build_footer_view(self.footer_view_frame)
        self._build_view_tabs()

        # ---- Upload gate (built last; sits on top until a file is loaded) -------------------------------
        self.upload_screen_frame = self._build_upload_screen()
        self.upload_screen_frame.pack(fill="both", expand=True)

    def _on_left_panel_mousewheel(self, event):
        """Always-on wheel handler: scrolls the left panel whenever the pointer is over it."""
        lc = getattr(self, "left_canvas", None)
        if lc is None or not lc.winfo_exists():
            return
        px, py = self.winfo_pointerxy()
        x, y = lc.winfo_rootx(), lc.winfo_rooty()
        if not (x <= px <= x + lc.winfo_width() and y <= py <= y + lc.winfo_height()):
            return
        if getattr(event, "num", None) == 4:
            lc.yview_scroll(-1, "units")
        elif getattr(event, "num", None) == 5:
            lc.yview_scroll(1, "units")
        else:
            lc.yview_scroll(int(-1 * (event.delta / 120)), "units")
