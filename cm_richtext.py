"""Rich text for the email message and footer.

Top half: pure functions (style runs -> HTML / plain text, {name}
substitution). Bottom half: RichTextEditor, a Tk Text widget with a small
formatting toolbar (bold/italic/underline/size/link) built on semantic tags.

Model: a document is a list of "runs" -
    {"text": str, "b": bool, "i": bool, "u": bool, "size": int|None, "href": str|None,
     "font": str|None}
(size None = the base size; font None = the default font, Arial). Runs are the source of truth: they're what gets
saved in settings.json and rendered to HTML at send time.
"""

import html
import re
import sys
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, messagebox, simpledialog

from cm_constants import (EMAIL_BASE_FONT_PX, FONT_SIZES_PX, NAME_PLACEHOLDER,
                          EMAIL_FONTS, DEFAULT_EMAIL_FONT)

BASE = EMAIL_BASE_FONT_PX
NAME_TOKEN_RE = re.compile(re.escape(NAME_PLACEHOLDER), re.IGNORECASE)
_PLACEHOLDER_RE = re.compile(r"\{[^{}]*\}")


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------
FONT_CSS = dict(EMAIL_FONTS)
FONT_INDEX = {name: i for i, (name, _css) in enumerate(EMAIL_FONTS)}


def _clean_font(font):
    """Known non-default font name, else None (drops unknown fonts from old/edited data)."""
    return font if font in FONT_CSS and font != DEFAULT_EMAIL_FONT else None


def make_run(text, b=False, i=False, u=False, size=None, href=None, font=None):
    return {"text": text, "b": bool(b), "i": bool(i), "u": bool(u),
            "size": None if (not size or size == BASE) else int(size), "href": href or None,
            "font": _clean_font(font)}


def _style(r):
    size = r.get("size")
    return (bool(r.get("b")), bool(r.get("i")), bool(r.get("u")),
            None if (not size or size == BASE) else int(size), r.get("href") or None,
            _clean_font(r.get("font")))


def normalize_runs(runs):
    """Drop empty runs and merge neighbours that share a style."""
    out = []
    for r in runs or []:
        text = r.get("text", "")
        if not text:
            continue
        if out and _style(out[-1]) == _style(r):
            out[-1]["text"] += text
        else:
            out.append(make_run(text, *_style(r)))
    return out


def runs_text(runs):
    return "".join(r.get("text", "") for r in runs or [])


def has_visible_text(runs):
    return bool(runs_text(runs).strip())


def find_unknown_placeholders(text):
    """{tokens} other than {name} - almost certainly typos."""
    return sorted({t for t in _PLACEHOLDER_RE.findall(text)
                   if t.lower() != NAME_PLACEHOLDER})


def substitute_name(runs, value):
    """Replace every {name} (even one split across differently-styled runs)
    with `value`, which takes the style of the token's first character."""
    runs = normalize_runs(runs)
    text = runs_text(runs)
    if not NAME_TOKEN_RE.search(text):
        return runs
    styles = []
    for r in runs:
        styles.extend([r] * len(r["text"]))
    out, pos = [], 0

    def emit(a, b):
        k = a
        while k < b:
            s, j = styles[k], k
            while j < b and styles[j] is s:
                j += 1
            out.append(dict(s, text=text[k:j]))
            k = j

    for m in NAME_TOKEN_RE.finditer(text):
        emit(pos, m.start())
        out.append(dict(styles[m.start()], text=value))
        pos = m.end()
    emit(pos, len(text))
    return normalize_runs(out)


def _run_to_html(r):
    t = html.escape(r["text"], quote=False)
    t = t.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>\n")
    t = re.sub(r" {2,}", lambda m: " " + "&nbsp;" * (len(m.group()) - 1), t)
    if r.get("b"):
        t = f"<b>{t}</b>"
    if r.get("i"):
        t = f"<i>{t}</i>"
    if r.get("u"):
        t = f"<u>{t}</u>"
    if r.get("href"):
        t = f'<a href="{html.escape(r["href"], quote=True)}" style="color:#1155cc;">{t}</a>'
    size, font = r.get("size"), _clean_font(r.get("font"))
    css = (f"font-family:{FONT_CSS[font]};" if font else "") + \
          (f"font-size:{int(size)}px;" if size and size != BASE else "")
    if css:
        t = f'<span style="{css}">{t}</span>'
    return t


def runs_to_html(runs):
    return "".join(_run_to_html(r) for r in normalize_runs(runs))


def runs_to_plain(runs):
    parts = []
    for r in normalize_runs(runs):
        t = r["text"]
        href = r.get("href")
        if href and t.strip() != href and t.strip() != href.replace("mailto:", ""):
            t = f"{t} ({href})"
        parts.append(t)
    return "".join(parts)


def normalize_url(url):
    """Return a safe http/https/mailto URL, or None if the scheme isn't allowed."""
    url = (url or "").strip()
    if not url:
        return None
    m = re.match(r"^([A-Za-z][A-Za-z0-9+.-]*):", url)
    if m:
        return url if m.group(1).lower() in ("http", "https", "mailto") else None
    if "@" in url and "/" not in url:
        return "mailto:" + url
    return "https://" + url


# ---------------------------------------------------------------------------
# Widget
# ---------------------------------------------------------------------------
_PROXY_TCL = r"""
set cmd [lindex $args 0]
if {$cmd eq "insert" && [llength $args] == 3} {
    lappend args [{TYPING}]
}
set code [catch {{ORIG} {*}$args} result opts]
if {$code == 0} {
    if {$cmd in {insert delete replace}
        || ($cmd eq "tag" && [lindex $args 1] in {add remove})
        || ($cmd eq "edit" && [lindex $args 1] in {undo redo})} {
        {NOTIFY}
    }
}
return -options $opts $result
"""


class _StyledText(tk.Text):
    """Text whose plain 'insert' calls (typing, paste) get the editor's current
    typing style, and which reports edits so a live preview can follow.

    Done with a small TCL proc wrapped around the real widget command, NOT a
    Python callback. A Python callback that raises (e.g. Tk's own copy/paste
    bindings probing 'sel.first' inside a Tcl catch) is remembered by tkinter
    and re-raised from mainloop() - that crashed the app. A Tcl proc forwards
    errors as ordinary Tcl errors, which the callers' catch/try handle.
    The two Python helpers below swallow every exception for the same reason."""

    def __init__(self, master, editor, **kw):
        tk.Text.__init__(self, master, **kw)
        self._editor = editor
        orig = self._w + "_orig"
        self._typing_cmd = self._w + "_typing"
        self._notify_cmd = self._w + "_notify"
        self.tk.createcommand(self._typing_cmd, self._typing_tags_safe)
        self.tk.createcommand(self._notify_cmd, self._notify_safe)
        self.tk.call("rename", self._w, orig)
        body = (_PROXY_TCL.replace("{TYPING}", self._typing_cmd)
                          .replace("{ORIG}", orig).replace("{NOTIFY}", self._notify_cmd))
        self.tk.call("proc", self._w, "args", body)
        self._orig_name = orig
        self.bind("<Destroy>", self._cleanup, add="+")

    def _typing_tags_safe(self):
        try:
            return self._editor.typing_tags()
        except Exception:
            return ()

    def _notify_safe(self):
        try:
            self._editor._schedule_change()
        except Exception:
            pass
        return ""

    def _cleanup(self, event):
        if event.widget is not self:
            return
        for name in (self._typing_cmd, self._notify_cmd):
            try:
                self.tk.deletecommand(name)
            except Exception:
                pass


class RichTextEditor(ttk.Frame):
    FAMILY = "Segoe UI"

    def __init__(self, parent, get_theme, show_insert_name=False, readonly=False, height=8,
                 family=None, paper=False, on_change=None):
        """paper=True draws it like the email itself (white page, dark text, email link
        colour) regardless of theme; on_change() fires (debounced) after every edit or
        style change - used for the live footer preview."""
        super().__init__(parent)
        self._get_theme = get_theme
        self._readonly = readonly
        self._family = family or DEFAULT_EMAIL_FONT
        self._paper = paper
        self._on_change = on_change
        self._change_job = None
        self._suppress = False
        self._link_color = "#1155cc" if paper else "#4d8dff"
        self._links = {}
        self._link_n = 0
        self._fonts = {}
        self._typing = {"b": False, "i": False, "u": False, "size": None, "font": None}
        self._tool_btns = {}
        self._base_font = tkfont.Font(family=self._family, size=-BASE)

        self.toolbar = tk.Frame(self)
        if not readonly:
            self.toolbar.pack(fill="x", pady=(0, 3))
            self._make_tool("b", "B", lambda: self.toggle_style("b"),
                            tkfont.Font(family=self.FAMILY, size=10, weight="bold"))
            self._make_tool("i", "I", lambda: self.toggle_style("i"),
                            tkfont.Font(family=self.FAMILY, size=10, slant="italic"))
            self._make_tool("u", "U", lambda: self.toggle_style("u"),
                            tkfont.Font(family=self.FAMILY, size=10, underline=1))
            self.font_var = tk.StringVar(value=DEFAULT_EMAIL_FONT)
            self.font_combo = ttk.Combobox(self.toolbar, textvariable=self.font_var, width=15, state="readonly",
                                           values=[name for name, _css in EMAIL_FONTS])
            self.font_combo.pack(side="left", padx=(8, 0))
            self.font_combo.bind("<<ComboboxSelected>>", lambda e: self.set_font(self.font_var.get()))
            self.size_var = tk.StringVar(value=str(BASE))
            self.size_combo = ttk.Combobox(self.toolbar, textvariable=self.size_var, width=4,
                                           state="readonly", values=[str(s) for s in FONT_SIZES_PX])
            self.size_combo.pack(side="left", padx=(8, 4))
            self.size_combo.bind("<<ComboboxSelected>>", lambda e: self.set_size(int(self.size_var.get())))
            self._make_tool("link", "Link", self.add_link, tkfont.Font(family=self.FAMILY, size=9, weight="bold"))
            if show_insert_name:
                self._make_tool("name", "Insert name", self.insert_name,
                                tkfont.Font(family=self.FAMILY, size=9, weight="bold"), right=True)

        body = tk.Frame(self)
        body.pack(fill="both", expand=True)
        self.text = _StyledText(body, self, wrap="word", undo=True, height=height, relief="flat",
                                padx=8, pady=6, highlightthickness=1, font=self._base_font)
        vsb = ttk.Scrollbar(body, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=vsb.set)
        self.text.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.text.tag_configure("fmt_u", underline=True)

        if not readonly:
            self.text.bind("<KeyRelease>", lambda e: self._sync_from_cursor(), add="+")
            self.text.bind("<ButtonRelease-1>", lambda e: self._sync_from_cursor(), add="+")
            self.text.bind("<<Selection>>", lambda e: self._refresh_toolbar(), add="+")
            for key, style in (("b", "b"), ("i", "i"), ("u", "u")):
                for k in (key, key.upper()):
                    self.text.bind(f"<Control-{k}>", lambda e, s=style: (self.toggle_style(s), "break")[1])
        else:
            self.text.configure(state="disabled", cursor="arrow")
        self.apply_theme()

    # ---- toolbar ---------------------------------------------------------
    def _make_tool(self, key, label, command, font, right=False):
        btn = tk.Label(self.toolbar, text=label, font=font, padx=9, pady=2, cursor="hand2", bd=0)
        btn.pack(side="right" if right else "left", padx=(0, 4))
        btn.bind("<Button-1>", lambda e: command())
        self._tool_btns[key] = btn

    def _refresh_toolbar(self):
        if self._readonly:
            return
        theme = self._get_theme()
        sel = self._selection()
        for key in ("b", "i", "u"):
            tag = f"fmt_{key}"
            if sel:
                on = all(tag in self.text.tag_names(ix) for ix in self._iter_chars(*sel))
            else:
                on = self._typing[key]
            btn = self._tool_btns[key]
            btn.configure(bg=theme["accent"] if on else theme["tab_inactive_bg"],
                          fg="#ffffff" if on else theme["text"])
        size, font = self._typing["size"] or BASE, self._typing["font"]
        if sel:
            a = self._attrs_at(sel[0])
            size, font = a["size"] or BASE, a["font"]
        self.size_var.set(str(size))
        self.font_var.set(font or DEFAULT_EMAIL_FONT)

    def apply_theme(self):
        theme = self._get_theme()
        self.toolbar.configure(bg=theme["dialog_bg"])
        for key, btn in self._tool_btns.items():
            if key in ("b", "i", "u"):
                continue
            btn.configure(bg=theme["accent2"], fg="#ffffff")
        if self._paper:
            self.text.configure(bg="#ffffff", fg="#222222", insertbackground="#222222",
                                highlightbackground=theme["border"], highlightcolor=theme["border"],
                                selectbackground="#cfe3ff", selectforeground="#222222")
        else:
            self.text.configure(bg=theme["entry_bg"], fg=theme["text"], insertbackground=theme["text"],
                                highlightbackground=theme["border"], highlightcolor=theme["accent"],
                                selectbackground=theme["accent"], selectforeground="#ffffff")
        self._refresh_toolbar()

    # ---- tag / font plumbing ----------------------------------------------
    def _font_tag(self, b, i, size, font=None):
        name = f"ft_{int(b)}{int(i)}_{size}_{FONT_INDEX.get(font, 'd')}"
        if name not in self._fonts:
            f = tkfont.Font(family=font or self._family, size=-int(size),
                            weight="bold" if b else "normal", slant="italic" if i else "roman")
            self._fonts[name] = f
            self.text.tag_configure(name, font=f)
        return name

    def typing_tags(self):
        t = self._typing
        tags = []
        if t["b"]:
            tags.append("fmt_b")
        if t["i"]:
            tags.append("fmt_i")
        if t["u"]:
            tags.append("fmt_u")
        if t["size"]:
            tags.append(f"size_{t['size']}")
        if t["font"]:
            tags.append(f"font_{FONT_INDEX[t['font']]}")
        tags.append(self._font_tag(t["b"], t["i"], t["size"] or BASE, t["font"]))
        return tuple(tags)

    def _attrs_at(self, index):
        names = set(self.text.tag_names(index))
        size, href, font = None, None, None
        for n in names:
            if n.startswith("size_"):
                size = int(n[5:])
            elif n.startswith("link_"):
                href = self._links.get(n)
            elif n.startswith("font_"):
                font = EMAIL_FONTS[int(n[5:])][0]
        return {"b": "fmt_b" in names, "i": "fmt_i" in names, "u": "fmt_u" in names,
                "size": size, "href": href, "font": font}

    def _selection(self):
        try:
            if not self.text.tag_ranges("sel"):
                return None
            return self.text.index("sel.first"), self.text.index("sel.last")
        except tk.TclError:
            return None

    def _iter_chars(self, start, end):
        ix = self.text.index(start)
        while self.text.compare(ix, "<", end):
            yield ix
            ix = self.text.index(f"{ix}+1c")

    def _refresh_fonts(self, start, end):
        for ix in self._iter_chars(start, end):
            a = self._attrs_at(ix)
            desired = self._font_tag(a["b"], a["i"], a["size"] or BASE, a["font"])
            current = [n for n in self.text.tag_names(ix) if n.startswith("ft_")]
            if current != [desired]:
                for n in current:
                    self.text.tag_remove(n, ix, f"{ix}+1c")
                self.text.tag_add(desired, ix, f"{ix}+1c")

    def _sync_from_cursor(self):
        if self.text.compare("insert", "==", "1.0"):
            a = self._attrs_at("1.0") if self.text.get("1.0", "end-1c") else \
                {"b": False, "i": False, "u": False, "size": None, "font": None}
        else:
            a = self._attrs_at("insert-1c")
        self._typing.update(b=a["b"], i=a["i"], u=a["u"], size=a["size"], font=a["font"])
        self._refresh_toolbar()

    # ---- actions -----------------------------------------------------------
    def toggle_style(self, key):
        sel = self._selection()
        if sel:
            tag = f"fmt_{key}"
            all_on = all(tag in self.text.tag_names(ix) for ix in self._iter_chars(*sel))
            (self.text.tag_remove if all_on else self.text.tag_add)(tag, *sel)
            self._refresh_fonts(*sel)
        else:
            self._typing[key] = not self._typing[key]
        self._refresh_toolbar()
        self.text.focus_set()

    def set_size(self, size):
        sel = self._selection()
        if sel:
            for n in self.text.tag_names():
                if n.startswith("size_"):
                    self.text.tag_remove(n, *sel)
            if size != BASE:
                self.text.tag_add(f"size_{size}", *sel)
            self._refresh_fonts(*sel)
        else:
            self._typing["size"] = None if size == BASE else size
        self.text.focus_set()

    def set_font(self, name):
        name = _clean_font(name)
        sel = self._selection()
        if sel:
            for n in self.text.tag_names():
                if n.startswith("font_"):
                    self.text.tag_remove(n, *sel)
            if name:
                self.text.tag_add(f"font_{FONT_INDEX[name]}", *sel)
            self._refresh_fonts(*sel)
        else:
            self._typing["font"] = name
        self._refresh_toolbar()
        self.text.focus_set()

    def _new_link_tag(self, url):
        self._link_n += 1
        tag = f"link_{self._link_n}"
        self._links[tag] = url
        self.text.tag_configure(tag, foreground=self._link_color, underline=True)
        return tag

    def add_link(self):
        sel = self._selection()
        if not sel:
            messagebox.showinfo("Insert link", "Select the text you want to turn into a link first.",
                                parent=self.winfo_toplevel())
            return
        existing = self._attrs_at(sel[0])["href"] or "https://"
        url = simpledialog.askstring("Insert link", "Web address (URL) - leave blank to remove the link:",
                                     parent=self.winfo_toplevel(), initialvalue=existing)
        if url is None:
            return
        for n in list(self._links):
            self.text.tag_remove(n, *sel)
        url = url.strip()
        if not url or url == "https://":
            return
        safe = normalize_url(url)
        if safe is None:
            messagebox.showerror("Insert link", "Only http, https and mailto links are allowed.",
                                 parent=self.winfo_toplevel())
            return
        self.text.tag_add(self._new_link_tag(safe), *sel)
        self.text.focus_set()

    def insert_name(self):
        self.text.insert("insert", NAME_PLACEHOLDER)
        self.text.focus_set()

    # ---- model <-> widget ----------------------------------------------------
    def get_runs(self):
        runs, active = [], set()
        for key, value, _index in self.text.dump("1.0", "end-1c", tag=True, text=True):
            if key == "tagon":
                active.add(value)
            elif key == "tagoff":
                active.discard(value)
            elif key == "text":
                size, href, font = None, None, None
                for n in active:
                    if n.startswith("size_"):
                        size = int(n[5:])
                    elif n.startswith("link_"):
                        href = self._links.get(n)
                    elif n.startswith("font_"):
                        font = EMAIL_FONTS[int(n[5:])][0]
                runs.append(make_run(value, "fmt_b" in active, "fmt_i" in active,
                                     "fmt_u" in active, size, href, font))
        return normalize_runs(runs)

    def _schedule_change(self):
        if self._on_change is None or self._suppress:
            return
        if self._change_job is not None:
            try:
                self.after_cancel(self._change_job)
            except Exception:
                pass
        self._change_job = self.after(60, self._fire_change)

    def _fire_change(self):
        self._change_job = None
        if self.winfo_exists() and self._on_change is not None:
            self._on_change()

    def set_runs(self, runs):
        self._suppress = True
        try:
            self._set_runs_impl(runs)
        finally:
            self._suppress = False

    def _set_runs_impl(self, runs):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        for r in normalize_runs(runs):
            tags = []
            if r.get("b"):
                tags.append("fmt_b")
            if r.get("i"):
                tags.append("fmt_i")
            if r.get("u"):
                tags.append("fmt_u")
            if r.get("size"):
                tags.append(f"size_{r['size']}")
            if r.get("href"):
                tags.append(self._new_link_tag(r["href"]))
            font = _clean_font(r.get("font"))
            if font:
                tags.append(f"font_{FONT_INDEX[font]}")
            tags.append(self._font_tag(r.get("b"), r.get("i"), r.get("size") or BASE, font))
            self.text.insert("end", r["text"], tuple(tags))
        self._typing.update(b=False, i=False, u=False, size=None, font=None)
        self.text.edit_reset()
        if self._readonly:
            self.text.configure(state="disabled")
        else:
            self._refresh_toolbar()

    def is_empty(self):
        return not self.text.get("1.0", "end-1c").strip()
