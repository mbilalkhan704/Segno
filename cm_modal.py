"""Modal-dialog attention system, exit confirmation, and small window
helpers - ported from Meraki's CoreMixin, split out so the core stays small."""

import ctypes
import math
import sys
import tkinter as tk
from tkinter import ttk
from ctypes import wintypes

from PIL import Image, ImageDraw, ImageTk

from cm_constants import APP_NAME


class _FLASHWINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("hwnd", ctypes.c_void_p),
                ("dwFlags", ctypes.c_uint), ("uCount", ctypes.c_uint),
                ("dwTimeout", ctypes.c_uint)]


class ModalMixin:
    # ---- window helpers ------------------------------------------------------
    def _hwnd(self, widget):
        h = widget.winfo_id()
        return ctypes.windll.user32.GetParent(h) or h

    def _maximize_window(self):
        try:
            self.state("zoomed")
        except tk.TclError:
            try:
                self.attributes("-zoomed", True)
            except tk.TclError:
                sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
                self.geometry(f"{sw}x{sh}+0+0")

    def _center_dialog(self, dialog, width=None, height=None):
        """Centre a dialog. Without an explicit size only the POSITION is set, so the dialog keeps
        auto-sizing to its content (a longer message can't push buttons out of view)."""
        dialog.update_idletasks()
        w = width or dialog.winfo_reqwidth()
        h = height or dialog.winfo_reqheight()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        pos = f"+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 3)}"
        dialog.geometry(pos if (width is None and height is None) else f"{w}x{h}{pos}")
        self._reveal_dialog(dialog)                # only now does it become visible - already in place

    def _new_dialog(self, title, resizable=False):
        """A themed, transient, grab-holding Toplevel registered for attention."""
        theme = self._current_theme_colors
        dialog = tk.Toplevel(self)
        dialog.withdraw()          # stay invisible while the content is built and positioned (no flash)
        dialog.title(title)
        dialog.configure(bg=theme["dialog_bg"])
        dialog.resizable(resizable, resizable)
        dialog.transient(self)
        self._register_modal_dialog(dialog)
        # _center_dialog() reveals it. Safety net in case a caller never calls it: a timer (not an idle
        # callback, which update_idletasks() would run too early) shows it a moment later.
        dialog.after(250, lambda: self._reveal_dialog(dialog))
        return dialog

    def _reveal_dialog(self, dialog):
        """Show a finished dialog (already positioned) and make it modal."""
        try:
            if not dialog.winfo_exists() or dialog.state() != "withdrawn":
                return
            dialog.deiconify()
            dialog.lift()
            self._grab_when_visible(dialog)
            dialog.focus_set()
        except tk.TclError:
            pass

    def _grab_when_visible(self, dialog, tries=20):
        try:
            dialog.grab_set()
        except tk.TclError:                       # not mapped yet - retry shortly
            if tries > 0 and dialog.winfo_exists():
                dialog.after(25, lambda: self._grab_when_visible(dialog, tries - 1))

    # ---- attention system -------------------------------------------------------
    def _user_is_off_dialog(self, target):
        if sys.platform.startswith("win"):
            try:
                return ctypes.windll.user32.GetForegroundWindow() == self._hwnd(self)
            except Exception:
                return False
        try:
            f = self.focus_get()
        except Exception:
            return False
        if f is None:
            return False
        s, t = str(f), str(target)
        return not (s == t or s.startswith(t + "."))

    def _register_modal_dialog(self, dialog):
        self._active_modal_dialogs.append(dialog)

        def _on_destroyed(event, d=dialog):
            if event.widget is d and d in self._active_modal_dialogs:
                self._active_modal_dialogs.remove(d)

        dialog.bind("<Destroy>", _on_destroyed, add="+")
        try:
            dialog.focus_set()
        except Exception:
            pass
        if not getattr(self, "_modal_focus_poll_running", False):
            self._modal_focus_poll_running = True
            self.after(400, self._poll_modal_focus)

    def _poll_modal_focus(self):
        alive = [d for d in self._active_modal_dialogs if d.winfo_exists()]
        if not alive:
            self._modal_focus_poll_running = False
            return
        target = alive[-1]
        if self._user_is_off_dialog(target) and not getattr(target, "_attn_cooldown", False):
            self._flash_dialog_attention(target)
            target._attn_cooldown = True
            self.after(1200, lambda: setattr(target, "_attn_cooldown", False))
        self.after(300, self._poll_modal_focus)

    def _flash_dialog_attention(self, dialog):
        if not dialog.winfo_exists():
            return
        try:
            if sys.platform.startswith("win"):
                import winsound
                winsound.MessageBeep()
            else:
                self.bell()
        except Exception:
            pass
        if sys.platform.startswith("win"):
            try:
                for w in (dialog, self):
                    info = _FLASHWINFO(ctypes.sizeof(_FLASHWINFO), self._hwnd(w), 3, 3, 0)
                    ctypes.windll.user32.FlashWindowEx(ctypes.byref(info))
            except Exception:
                pass
        try:
            dialog.deiconify()
            dialog.lift()
            dialog.focus_force()
            dialog.grab_set()
        except Exception:
            pass
        self._pulse_dialog(dialog)

    def _pulse_dialog(self, dialog, step=0, edges=None):
        if not dialog.winfo_exists():
            return
        if edges is None:
            t, edges = 4, []
            try:
                for kw in (dict(x=0, y=0, relwidth=1, height=t),
                           dict(x=0, rely=1, relwidth=1, height=t, anchor="sw"),
                           dict(x=0, y=0, width=t, relheight=1),
                           dict(relx=1, y=0, width=t, relheight=1, anchor="ne")):
                    f = tk.Frame(dialog, bg="#ff4d4d", bd=0, highlightthickness=0)
                    f.place(**kw)
                    edges.append(f)
            except Exception:
                return
        if step >= 9:
            for f in edges:
                try:
                    f.destroy()
                except Exception:
                    pass
            return
        color = "#ff4d4d" if step % 2 == 0 else "#ffd43b"
        for f in edges:
            try:
                f.configure(bg=color)
                f.lift()
            except Exception:
                pass
        self.after(40, lambda: self._pulse_dialog(dialog, step + 1, edges))

    def _install_close_hook(self):
        """Windows: catch the title-bar X at OS level so it still reaches us
        while a dialog holds a Tk grab (flashes the dialog instead of closing)."""
        if not sys.platform.startswith("win"):
            return
        try:
            WM_CLOSE, WM_SYSCOMMAND, SC_CLOSE, SC_MINIMIZE, GWLP_WNDPROC = 0x0010, 0x0112, 0xF060, 0xF020, -4
            user32 = ctypes.windll.user32
            LRESULT = ctypes.c_ssize_t
            WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, ctypes.c_uint,
                                         wintypes.WPARAM, wintypes.LPARAM)
            user32.SetWindowLongPtrW.restype = ctypes.c_void_p
            user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
            user32.CallWindowProcW.restype = LRESULT
            user32.CallWindowProcW.argtypes = [ctypes.c_void_p, wintypes.HWND, ctypes.c_uint,
                                               wintypes.WPARAM, wintypes.LPARAM]

            def proc(hwnd, msg, wparam, lparam):
                try:
                    cmd = wparam & 0xFFF0
                    if msg == WM_CLOSE or (msg == WM_SYSCOMMAND and cmd in (SC_CLOSE, SC_MINIMIZE)):
                        alive = [d for d in self._active_modal_dialogs if d.winfo_exists()]
                        if alive:
                            self.after_idle(lambda: self._flash_dialog_attention(alive[-1]))
                            return 0
                except Exception:
                    pass
                return user32.CallWindowProcW(self._old_wndproc, hwnd, msg, wparam, lparam)

            self._new_wndproc = WNDPROC(proc)   # keep a reference or it is garbage collected
            self._old_wndproc = user32.SetWindowLongPtrW(
                self._hwnd(self), GWLP_WNDPROC, ctypes.cast(self._new_wndproc, ctypes.c_void_p))
        except Exception:
            pass

    # ---- exit confirmation --------------------------------------------------------
    def _make_exit_icon(self, size=32, color="#e03131"):
        s = size * 4
        img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        w, pad = int(s * 0.11), s * 0.16
        cx, cy = s / 2, s / 2 + s * 0.04
        d.arc((pad, cy - (s / 2 - pad), s - pad, cy + (s / 2 - pad)), start=-50, end=230, fill=color, width=w)
        top, bottom = s * 0.10, s * 0.50
        d.line((cx, top, cx, bottom), fill=color, width=w)
        rc = (s / 2 - pad) - w / 2
        caps = [(cx, top), (cx, bottom)]
        for a in (-50, 230):
            caps.append((cx + rc * math.cos(math.radians(a)), cy + rc * math.sin(math.radians(a))))
        for x, y in caps:
            d.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=color)
        return ImageTk.PhotoImage(img.resize((size, size), Image.LANCZOS))

    def _on_close_request(self):
        alive = [d for d in self._active_modal_dialogs if d.winfo_exists()]
        if alive:
            self._flash_dialog_attention(alive[-1])
            return
        sending = getattr(self, "_sending", False)
        dialog = self._new_dialog(f"Exit {APP_NAME}")
        dialog._is_exit_prompt = True
        try:
            self._exit_icon_small = self._make_exit_icon(32)
            self._exit_icon_big = self._make_exit_icon(56)
            dialog.iconphoto(False, self._exit_icon_small)
        except Exception:
            self._exit_icon_big = None

        frm = ttk.Frame(dialog, padding=22, style="Dialog.TFrame")
        frm.pack(fill="both", expand=True)
        body = ttk.Frame(frm, style="Dialog.TFrame")
        body.pack(pady=(0, 18))
        if self._exit_icon_big is not None:
            ttk.Label(body, image=self._exit_icon_big, style="Dialog.TLabel").pack(side="left", padx=(0, 16))
        txt = ttk.Frame(body, style="Dialog.TFrame")
        txt.pack(side="left")
        ttk.Label(txt, text="Are you sure you want to exit?", font=("Segoe UI", 12, "bold"),
                  style="Dialog.TLabel").pack(anchor="w", pady=(0, 4))
        dirty = getattr(self, "_footer_tab_open", False) and self._footer_is_dirty()
        note = ("A send is in progress. Exiting stops it - emails already sent stay sent,\n"
                "and the rest can be sent later." if sending else
                "You have unsaved changes in the Footer tab." if dirty else
                "Your subject and message are not saved between sessions.")
        ttk.Label(txt, text=note, style="DialogSubtle.TLabel").pack(anchor="w")

        btn_row = ttk.Frame(frm, style="Dialog.TFrame")
        btn_row.pack()

        def do_exit():
            try:
                self._cancel_event.set()
            except Exception:
                pass
            dialog.destroy()
            self.destroy()

        cancel_btn = ttk.Button(btn_row, text="Cancel", command=dialog.destroy)
        cancel_btn.pack(side="left", padx=6)
        ttk.Button(btn_row, text="Exit", command=do_exit).pack(side="left", padx=6)
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        dialog.bind("<Escape>", lambda e: dialog.destroy())
        self._center_dialog(dialog)
        cancel_btn.focus_set()
