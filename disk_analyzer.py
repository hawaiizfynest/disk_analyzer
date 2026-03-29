"""
DiskAnalyzer - Windows GUI Disk Space Analyzer
Requires Python 3.7+ (tkinter is included with Python on Windows)
Run: python disk_analyzer.py
Build to EXE: pip install pyinstaller && pyinstaller --onefile --windowed disk_analyzer.py
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import os
import shutil
import subprocess
import winreg
import datetime


# ── Colour palette ──────────────────────────────────────────────────────────
BG        = "#0e0e0e"
BG2       = "#141414"
BG3       = "#1a1a1a"
BORDER    = "#252525"
FG        = "#e0e0e0"
FG_DIM    = "#666666"
FG_HINT   = "#444444"
RED       = "#FF4136"
YELLOW    = "#FFDC00"
GREEN     = "#2ECC40"
BLUE      = "#00B4D8"
PURPLE    = "#7B2FBE"
ORANGE    = "#FF851B"
ACCENT    = RED

TYPE_COLOR = {
    "System": "#FF4136",
    "Apps":   "#00B4D8",
    "User":   "#2ECC40",
    "Cache":  "#FFDC00",
    "Other":  "#888888",
}

BAR_COLORS = [RED, BLUE, GREEN, YELLOW, PURPLE,
              ORANGE, "#FF6B9D", "#01FFE4", "#F5A623", "#A8E6CF"]

FONT_MONO  = ("Consolas", 10)
FONT_SMALL = ("Consolas", 9)
FONT_HEAD  = ("Consolas", 9, "bold")


# ── Helpers ──────────────────────────────────────────────────────────────────
def fmt_bytes(b):
    if b is None or b < 0: return "—"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024: return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.2f} PB"

def get_folder_size(path):
    total, count = 0, 0
    try:
        with os.scandir(path) as it:
            for entry in it:
                try:
                    if entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        s, c = get_folder_size(entry.path)
                        total += s; count += c
                    else:
                        total += entry.stat(follow_symlinks=False).st_size
                        count += 1
                except (PermissionError, OSError):
                    pass
    except (PermissionError, OSError):
        pass
    return total, count

def classify(name, path):
    n = name.lower()
    p = path.lower()
    if n in ("windows", "winnt"):                                      return "System"
    if n in ("pagefile.sys", "hiberfil.sys", "swapfile.sys",
             "$recycle.bin", "$winreagent",
             "system volume information", "recovery", "boot"):         return "System"
    if "program files" in n:                                           return "Apps"
    if "programdata" in n:                                             return "Apps"
    if "appdata\\local" in p or "appdata/local" in p:                 return "Cache"
    if "appdata\\roaming" in p or "appdata/roaming" in p:             return "Cache"
    if "cache" in n:                                                   return "Cache"
    if "users" in n:                                                   return "User"
    return "Other"

def open_in_explorer(path):
    try:
        if os.path.isfile(path):
            subprocess.Popen(["explorer", "/select,", path])
        else:
            subprocess.Popen(["explorer", path])
    except Exception:
        pass

def _darken(hex_color, amount=0.3):
    h = hex_color.lstrip("#")
    rgb = tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
    rgb = tuple(max(0, int(c * (1 - amount))) for c in rgb)
    return "#{:02x}{:02x}{:02x}".format(*rgb)


# ── Squarify treemap layout ───────────────────────────────────────────────────
def squarify(items, x, y, w, h):
    if not items: return []
    total = sum(s for _, s in items)
    if total == 0 or w <= 0 or h <= 0: return []
    result = []
    remaining = list(items)

    def layout_row(row, x, y, w, h, horiz):
        row_total = sum(s for _, s in row)
        if row_total == 0: return
        pos = x if horiz else y
        for name, s in row:
            frac = s / row_total
            if horiz:
                result.append((name, x, pos, w, frac * h)); pos += frac * h
            else:
                result.append((name, pos, y, frac * w, h)); pos += frac * w

    while remaining:
        if w >= h:
            row, rest, used = [], [], 0
            for item in remaining:
                frac = item[1] / total
                if used + frac <= remaining[0][1] / total * (w / h) + 1e-9 or not row:
                    row.append(item); used += frac
                else:
                    rest.append(item)
            if not rest:
                layout_row(row, x, y, w, h, False); break
            row_h = used * h
            layout_row(row, x, y, w, row_h, False)
            y += row_h; h -= row_h; total -= sum(s for _, s in row); remaining = rest
        else:
            row, rest, used = [], [], 0
            for item in remaining:
                frac = item[1] / total
                if used + frac <= remaining[0][1] / total * (h / w) + 1e-9 or not row:
                    row.append(item); used += frac
                else:
                    rest.append(item)
            if not rest:
                layout_row(row, x, y, w, h, True); break
            row_w = used * w
            layout_row(row, x, y, row_w, h, True)
            x += row_w; w -= row_w; total -= sum(s for _, s in row); remaining = rest
    return result


# ── Windows Registry program reader ──────────────────────────────────────────
UNINSTALL_KEYS = [
    (winreg.HKEY_LOCAL_MACHINE,
     r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_LOCAL_MACHINE,
     r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_CURRENT_USER,
     r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
]

def read_installed_programs():
    programs = {}
    for hive, key_path in UNINSTALL_KEYS:
        try:
            key = winreg.OpenKey(hive, key_path)
            for i in range(winreg.QueryInfoKey(key)[0]):
                try:
                    sub_name = winreg.EnumKey(key, i)
                    sub = winreg.OpenKey(key, sub_name)

                    def rval(n, default=None, _sub=sub):
                        try: return winreg.QueryValueEx(_sub, n)[0]
                        except Exception: return default

                    name = rval("DisplayName")
                    if not name:
                        winreg.CloseKey(sub); continue

                    system_comp = rval("SystemComponent", 0)
                    if system_comp == 1:
                        winreg.CloseKey(sub); continue

                    size_kb   = rval("EstimatedSize")
                    version   = rval("DisplayVersion", "")
                    publisher = rval("Publisher", "")
                    inst_loc  = rval("InstallLocation", "")
                    inst_date = rval("InstallDate", "")
                    uninstall = rval("UninstallString", "")

                    date_str = ""
                    if inst_date and len(inst_date) == 8:
                        try:
                            d = datetime.datetime.strptime(inst_date, "%Y%m%d")
                            date_str = d.strftime("%Y-%m-%d")
                        except Exception:
                            date_str = inst_date

                    size_bytes = int(size_kb) * 1024 if size_kb else -1

                    if name not in programs or size_bytes > programs[name]["size"]:
                        programs[name] = {
                            "name":         name,
                            "version":      version,
                            "publisher":    publisher,
                            "size":         size_bytes,
                            "install_loc":  inst_loc,
                            "install_date": date_str,
                            "uninstall":    uninstall,
                        }
                    winreg.CloseKey(sub)
                except Exception:
                    pass
            winreg.CloseKey(key)
        except Exception:
            pass
    return list(programs.values())


# ── Main Application ──────────────────────────────────────────────────────────
class DiskAnalyzer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("DiskAnalyzer")
        self.geometry("1150x840")
        self.minsize(900, 640)
        self.configure(bg=BG)
        self._set_icon()

        # Disk state
        self.scan_root  = tk.StringVar(value="C:\\")
        self.results    = []
        self.scanning   = False
        self.total_disk = self.used_disk = self.free_disk = 0
        self._abort     = threading.Event()
        self._sort_col  = "size"
        self._sort_rev  = True
        self._hovered_tm = None

        # Programs state
        self.programs      = []
        self.prog_sort_col = "size"
        self.prog_sort_rev = True
        self.prog_scanning = False
        self._prog_hovered_tm = None

        self._build_ui()
        self._style_ttk()

    def _set_icon(self):
        try:
            img = tk.PhotoImage(width=16, height=16)
            img.put(RED, to=(0, 0, 15, 15))
            self.iconphoto(True, img)
        except Exception:
            pass

    def _style_ttk(self):
        s = ttk.Style(self)
        s.theme_use("default")
        s.configure("Treeview",
            background=BG2, foreground=FG, fieldbackground=BG2,
            borderwidth=0, rowheight=24, font=FONT_MONO)
        s.configure("Treeview.Heading",
            background=BG3, foreground=FG_DIM, relief="flat", font=FONT_HEAD)
        s.map("Treeview",
            background=[("selected", "#1a2a1a")],
            foreground=[("selected", FG)])
        s.map("Treeview.Heading",
            background=[("active", BORDER)])
        s.configure("Vertical.TScrollbar",
            background=BG3, troughcolor=BG, borderwidth=0, arrowcolor=FG_DIM)
        s.configure("TProgressbar",
            troughcolor=BG3, background=GREEN, borderwidth=0)
        s.configure("TNotebook",
            background=BG, borderwidth=0, tabmargins=[0, 0, 0, 0])
        s.configure("TNotebook.Tab",
            background=BG3, foreground=FG_DIM,
            font=("Consolas", 10, "bold"), padding=[22, 9])
        s.map("TNotebook.Tab",
            background=[("selected", BG)],
            foreground=[("selected", GREEN)])

    # ── Top-level UI ──────────────────────────────────────────────────────────
    def _build_ui(self):
        # Header
        hdr = tk.Frame(self, bg=BG, pady=12, padx=18)
        hdr.pack(fill="x")
        tk.Label(hdr, text="DISK ANALYZER", bg=BG, fg=FG,
                 font=("Consolas", 16, "bold")).pack(side="left")
        tk.Label(hdr, text="Windows Storage Inspector", bg=BG, fg=FG_HINT,
                 font=("Consolas", 9)).pack(side="left", padx=14, pady=4)
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        # Tabs
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True)
        self.tab_disk  = tk.Frame(self.nb, bg=BG)
        self.tab_progs = tk.Frame(self.nb, bg=BG)
        self.nb.add(self.tab_disk,  text="  💾  DISK SPACE  ")
        self.nb.add(self.tab_progs, text="  📦  INSTALLED PROGRAMS  ")
        self.nb.bind("<<NotebookTabChanged>>", self._on_tab_change)

        self._build_disk_tab()
        self._build_programs_tab()

        # Footer
        foot = tk.Frame(self, bg=BG3, pady=6, padx=18)
        foot.pack(fill="x", side="bottom")
        tk.Label(foot,
            text="Double-click row → open in Explorer  ·  Right-click → more options",
            bg=BG3, fg=FG_HINT, font=FONT_SMALL).pack(side="left")
        tk.Label(foot, text="DiskAnalyzer — github.com/YOUR_USERNAME/disk-analyzer",
            bg=BG3, fg=FG_HINT, font=FONT_SMALL).pack(side="right")

    def _on_tab_change(self, _event):
        if self.nb.index(self.nb.select()) == 1:
            if not self.programs and not self.prog_scanning:
                self._load_programs()

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 1 — DISK SPACE
    # ══════════════════════════════════════════════════════════════════════════
    def _build_disk_tab(self):
        p = self.tab_disk

        # Controls row
        ctrl = tk.Frame(p, bg=BG, pady=10, padx=18)
        ctrl.pack(fill="x")
        tk.Label(ctrl, text="Drive / Folder:", bg=BG, fg=FG_DIM,
                 font=FONT_SMALL).pack(side="left", padx=(0, 6))
        tk.Entry(ctrl, textvariable=self.scan_root, width=14,
            bg=BG3, fg=FG, insertbackground=FG, relief="flat",
            font=FONT_MONO, highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=ACCENT
        ).pack(side="left", padx=(0, 6))
        tk.Button(ctrl, text="Browse…", command=self._browse,
            bg=BG3, fg=FG_DIM, relief="flat", font=FONT_SMALL,
            activebackground=BORDER, activeforeground=FG,
            padx=8, pady=4, cursor="hand2").pack(side="left", padx=(0, 10))
        self.scan_btn = tk.Button(ctrl, text="▶  SCAN",
            command=self._toggle_scan, bg=ACCENT, fg="#fff", relief="flat",
            font=("Consolas", 11, "bold"),
            activebackground="#cc3329", activeforeground="#fff",
            padx=16, pady=6, cursor="hand2")
        self.scan_btn.pack(side="left")

        # Stats strip
        sf = tk.Frame(p, bg=BG, pady=8, padx=18)
        sf.pack(fill="x")
        self.stat_labels = {}
        for key, lbl, color in [
            ("path",  "PATH",   FG_DIM),
            ("total", "TOTAL",  FG_DIM),
            ("used",  "USED",   RED),
            ("free",  "FREE",   GREEN),
            ("pct",   "% USED", YELLOW),
        ]:
            f = tk.Frame(sf, bg=BG); f.pack(side="left", padx=(0, 32))
            tk.Label(f, text=lbl, bg=BG, fg=FG_HINT,
                     font=("Consolas", 8)).pack(anchor="w")
            w = tk.Label(f, text="—", bg=BG, fg=color,
                         font=("Consolas", 13, "bold"))
            w.pack(anchor="w")
            self.stat_labels[key] = w

        # Progress
        pf = tk.Frame(p, bg=BG, padx=18)
        pf.pack(fill="x", pady=(0, 6))
        self.progress = ttk.Progressbar(pf, mode="determinate")
        self.progress.pack(fill="x", pady=(0, 3))
        self.status_var = tk.StringVar(value="Enter a path and press SCAN.")
        tk.Label(pf, textvariable=self.status_var, bg=BG, fg=FG_DIM,
                 font=FONT_SMALL, anchor="w").pack(fill="x")

        tk.Frame(p, bg=BORDER, height=1).pack(fill="x")

        # Treemap
        tmf = tk.Frame(p, bg=BG, padx=18, pady=8)
        tmf.pack(fill="x")
        tk.Label(tmf, text="SPACE MAP", bg=BG, fg=FG_HINT,
                 font=("Consolas", 8)).pack(anchor="w")
        self.tm_canvas = tk.Canvas(tmf, bg=BG2, height=120,
            highlightthickness=1, highlightbackground=BORDER)
        self.tm_canvas.pack(fill="x")
        self.tm_canvas.bind("<Motion>",   self._tm_hover)
        self.tm_canvas.bind("<Leave>",    self._tm_leave)
        self.tm_canvas.bind("<Button-1>", self._tm_click)
        self._tm_rects = []
        self.tm_tip = tk.Label(tmf, text="", bg=BG3, fg=FG,
            font=FONT_SMALL, padx=10, pady=3, anchor="w")
        self.tm_tip.pack(fill="x", pady=(3, 0))

        tk.Frame(p, bg=BORDER, height=1).pack(fill="x")

        # Table
        tf = tk.Frame(p, bg=BG, padx=18, pady=8)
        tf.pack(fill="both", expand=True)
        hdr = tk.Frame(tf, bg=BG); hdr.pack(fill="x", pady=(0, 5))
        tk.Label(hdr, text="DIRECTORY BREAKDOWN", bg=BG, fg=FG_HINT,
                 font=("Consolas", 8)).pack(side="left")
        tk.Label(hdr, text="Filter:", bg=BG, fg=FG_DIM,
                 font=FONT_SMALL).pack(side="right", padx=(6, 0))
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *_: self._apply_filter())
        tk.Entry(hdr, textvariable=self.filter_var, width=18,
            bg=BG3, fg=FG, insertbackground=FG, relief="flat",
            font=FONT_MONO, highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=BLUE
        ).pack(side="right")

        cols = ("path", "size", "pct", "items", "type")
        self.tree = ttk.Treeview(tf, columns=cols, show="headings",
                                  selectmode="browse")
        for cid, lbl, w, anc in [
            ("path",  "PATH",       460, "w"),
            ("size",  "SIZE",       100, "e"),
            ("pct",   "% OF USED",   90, "e"),
            ("items", "ITEMS",        90, "e"),
            ("type",  "TYPE",         80, "center"),
        ]:
            self.tree.heading(cid, text=lbl,
                command=lambda c=cid: self._sort(c))
            self.tree.column(cid, width=w, anchor=anc,
                             stretch=(cid == "path"))
        vsb = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", self._open_selected)
        self.tree.bind("<Button-3>", self._right_click)
        for t, c in TYPE_COLOR.items():
            self.tree.tag_configure(t, foreground=c)
        self.tree.tag_configure("big", font=("Consolas", 10, "bold"))

        self.ctx_menu = tk.Menu(self, tearoff=0, bg=BG3, fg=FG,
            activebackground=BORDER, activeforeground=FG, font=FONT_SMALL)
        self.ctx_menu.add_command(label="Open in Explorer",
            command=self._open_selected)
        self.ctx_menu.add_command(label="Copy path",
            command=self._copy_path)

    # ── Disk tab logic ────────────────────────────────────────────────────────
    def _browse(self):
        d = filedialog.askdirectory(initialdir=self.scan_root.get())
        if d: self.scan_root.set(d)

    def _toggle_scan(self):
        if self.scanning:
            self._abort.set()
            self.scan_btn.config(text="▶  SCAN", bg=ACCENT)
            self.status_var.set("Scan aborted.")
            self.scanning = False
        else:
            self._start_scan()

    def _start_scan(self):
        root_path = self.scan_root.get().strip()
        if not os.path.isdir(root_path):
            messagebox.showerror("Invalid path",
                f"Cannot find directory:\n{root_path}"); return
        self._abort.clear()
        self.results = []; self.scanning = True
        self.scan_btn.config(text="■  STOP", bg="#555")
        self.progress["value"] = 0
        for iid in self.tree.get_children(): self.tree.delete(iid)
        self._clear_treemap(); self.tm_tip.config(text="")
        self.status_var.set(f"Scanning {root_path} …")
        try:
            u = shutil.disk_usage(root_path)
            self.total_disk, self.used_disk, self.free_disk = u.total, u.used, u.free
        except Exception:
            self.total_disk = self.used_disk = self.free_disk = 0
        self._update_stats(root_path)
        threading.Thread(target=self._scan_thread,
                         args=(root_path,), daemon=True).start()

    def _scan_thread(self, root_path):
        items = []
        try:
            entries = list(os.scandir(root_path))
        except PermissionError:
            self.after(0, lambda: self.status_var.set("Permission denied."))
            self.after(0, self._scan_done); return
        total = len(entries)
        for idx, entry in enumerate(entries):
            if self._abort.is_set(): break
            pct = int((idx / max(total, 1)) * 100)
            self.after(0, lambda p=pct, n=entry.name:
                (self.status_var.set(f"Scanning {n}… ({p}%)"),
                 self.progress.configure(value=p)))
            try:
                if entry.is_symlink(): continue
                if entry.is_dir(follow_symlinks=False):
                    size, count = get_folder_size(entry.path)
                    items.append({"name": entry.name, "path": entry.path,
                                  "size": size, "items": count,
                                  "type": classify(entry.name, entry.path),
                                  "is_file": False})
                else:
                    st = entry.stat(follow_symlinks=False)
                    items.append({"name": entry.name, "path": entry.path,
                                  "size": st.st_size, "items": 1,
                                  "type": classify(entry.name, entry.path),
                                  "is_file": True})
            except (PermissionError, OSError):
                pass
        self.results = sorted(items, key=lambda x: x["size"], reverse=True)
        self.after(0, self._scan_done)

    def _scan_done(self):
        self.scanning = False
        self.scan_btn.config(text="▶  SCAN", bg=ACCENT)
        self.progress["value"] = 100
        total_items = sum(r["items"] for r in self.results)
        self.status_var.set(
            f"Done — {len(self.results)} entries · {total_items:,} files · "
            "Double-click to open in Explorer")
        self._populate_tree(); self._draw_treemap()

    def _update_stats(self, path):
        pct = (self.used_disk / self.total_disk * 100) if self.total_disk else 0
        self.stat_labels["path"].config(text=path)
        self.stat_labels["total"].config(text=fmt_bytes(self.total_disk))
        self.stat_labels["used"].config(text=fmt_bytes(self.used_disk))
        self.stat_labels["free"].config(text=fmt_bytes(self.free_disk))
        self.stat_labels["pct"].config(text=f"{pct:.1f}%")

    def _populate_tree(self, data=None):
        for iid in self.tree.get_children(): self.tree.delete(iid)
        for r in (data or self.results):
            pct = (r["size"] / self.used_disk * 100) if self.used_disk else 0
            tags = [r["type"]]
            if r["size"] > 5 * 1024**3: tags.append("big")
            self.tree.insert("", "end",
                values=(r["path"], fmt_bytes(r["size"]),
                        f"{pct:.1f}%", f'{r["items"]:,}', r["type"]),
                tags=tags, iid=r["path"])

    def _sort(self, col):
        self._sort_rev = not self._sort_rev if self._sort_col == col else True
        self._sort_col = col
        key = {"size": lambda r: r["size"], "items": lambda r: r["items"],
               "type": lambda r: r["type"], "pct": lambda r: r["size"]
               }.get(col, lambda r: r["path"].lower())
        self.results.sort(key=key, reverse=self._sort_rev)
        self._apply_filter()

    def _apply_filter(self):
        q = self.filter_var.get().lower()
        data = [r for r in self.results
                if q in r["path"].lower() or q in r["type"].lower()] if q else None
        self._populate_tree(data)

    def _open_selected(self, _event=None):
        sel = self.tree.selection()
        if sel: open_in_explorer(sel[0])

    def _copy_path(self):
        sel = self.tree.selection()
        if sel: self.clipboard_clear(); self.clipboard_append(sel[0])

    def _right_click(self, event):
        row = self.tree.identify_row(event.y)
        if row:
            self.tree.selection_set(row)
            self.ctx_menu.post(event.x_root, event.y_root)

    def _clear_treemap(self):
        self.tm_canvas.delete("all"); self._tm_rects = []

    def _draw_treemap(self):
        self._clear_treemap()
        if not self.results: return
        self.tm_canvas.update_idletasks()
        W, H = self.tm_canvas.winfo_width(), self.tm_canvas.winfo_height()
        if W < 10 or H < 10: return
        items = [(r["path"], r["size"]) for r in self.results if r["size"] > 0]
        layout = squarify(items, 2, 2, W - 4, H - 4)
        lookup = {r["path"]: r for r in self.results}
        for path, rx, ry, rw, rh in layout:
            r = lookup.get(path)
            if not r: continue
            c = TYPE_COLOR.get(r["type"], "#888")
            rid = self.tm_canvas.create_rectangle(rx, ry, rx+rw, ry+rh,
                fill=_darken(c, 0.15), outline=c, width=1)
            tid = None
            if rw > 50 and rh > 22:
                label = r["name"] if rw > 80 else r["name"][:int(rw/7)]
                tid = self.tm_canvas.create_text(rx+rw/2, ry+rh/2,
                    text=f"{label}\n{fmt_bytes(r['size'])}",
                    fill=FG, font=("Consolas", 8),
                    justify="center", width=rw-4)
            self._tm_rects.append((rid, tid, r, rx, ry, rx+rw, ry+rh))

    def _tm_find(self, x, y):
        for rid, tid, r, x1, y1, x2, y2 in self._tm_rects:
            if x1 <= x <= x2 and y1 <= y <= y2: return rid, r
        return None, None

    def _tm_hover(self, event):
        rid, r = self._tm_find(event.x, event.y)
        if r:
            pct = (r["size"] / self.used_disk * 100) if self.used_disk else 0
            self.tm_tip.config(
                text=f"  {r['path']}   ·   {fmt_bytes(r['size'])}   "
                     f"·   {pct:.1f}% of used   ·   {r['items']:,} items   ·   {r['type']}",
                fg=TYPE_COLOR.get(r["type"], FG))
            if rid != self._hovered_tm:
                if self._hovered_tm:
                    self.tm_canvas.itemconfig(self._hovered_tm, width=1)
                self.tm_canvas.itemconfig(rid, width=2)
                self._hovered_tm = rid
        else:
            self.tm_tip.config(text="", fg=FG)

    def _tm_leave(self, _event):
        self.tm_tip.config(text="")
        if self._hovered_tm:
            self.tm_canvas.itemconfig(self._hovered_tm, width=1)
            self._hovered_tm = None

    def _tm_click(self, event):
        _, r = self._tm_find(event.x, event.y)
        if r:
            try: self.tree.selection_set(r["path"]); self.tree.see(r["path"])
            except Exception: pass

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 2 — INSTALLED PROGRAMS
    # ══════════════════════════════════════════════════════════════════════════
    def _build_programs_tab(self):
        p = self.tab_progs

        # Controls
        ctrl = tk.Frame(p, bg=BG, pady=10, padx=18)
        ctrl.pack(fill="x")
        self.prog_scan_btn = tk.Button(ctrl, text="🔄  REFRESH",
            command=self._load_programs, bg=BLUE, fg="#fff", relief="flat",
            font=("Consolas", 11, "bold"),
            activebackground="#0090b0", activeforeground="#fff",
            padx=16, pady=6, cursor="hand2")
        self.prog_scan_btn.pack(side="left")
        self.prog_status = tk.Label(ctrl,
            text="Switch to this tab to load installed programs.",
            bg=BG, fg=FG_DIM, font=FONT_SMALL)
        self.prog_status.pack(side="left", padx=16)

        right = tk.Frame(ctrl, bg=BG); right.pack(side="right")
        self.prog_uninstall_btn = tk.Button(right,
            text="🗑  UNINSTALL SELECTED",
            command=self._uninstall_selected,
            bg=BG3, fg=RED, relief="flat",
            font=("Consolas", 9, "bold"),
            activebackground=BORDER, activeforeground=RED,
            padx=12, pady=6, cursor="hand2", state="disabled")
        self.prog_uninstall_btn.pack(side="right", padx=(8, 0))
        tk.Label(right, text="Filter:", bg=BG, fg=FG_DIM,
                 font=FONT_SMALL).pack(side="right", padx=(8, 4))
        self.prog_filter_var = tk.StringVar()
        self.prog_filter_var.trace_add("write", lambda *_: self._apply_prog_filter())
        tk.Entry(right, textvariable=self.prog_filter_var, width=22,
            bg=BG3, fg=FG, insertbackground=FG, relief="flat",
            font=FONT_MONO, highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=BLUE
        ).pack(side="right")

        tk.Frame(p, bg=BORDER, height=1).pack(fill="x")

        # Summary stats
        sf = tk.Frame(p, bg=BG, pady=8, padx=18)
        sf.pack(fill="x")
        self.prog_stat_labels = {}
        for key, lbl, color in [
            ("count",   "PROGRAMS",   FG_DIM),
            ("known",   "KNOWN SIZE", BLUE),
            ("largest", "LARGEST",    RED),
            ("pubs",    "PUBLISHERS", PURPLE),
        ]:
            f = tk.Frame(sf, bg=BG); f.pack(side="left", padx=(0, 32))
            tk.Label(f, text=lbl, bg=BG, fg=FG_HINT,
                     font=("Consolas", 8)).pack(anchor="w")
            w = tk.Label(f, text="—", bg=BG, fg=color,
                         font=("Consolas", 13, "bold"))
            w.pack(anchor="w")
            self.prog_stat_labels[key] = w

        tk.Frame(p, bg=BORDER, height=1).pack(fill="x")

        # Programs treemap
        ptmf = tk.Frame(p, bg=BG, padx=18, pady=8)
        ptmf.pack(fill="x")
        tk.Label(ptmf, text="SIZE MAP  (programs with known size only)",
                 bg=BG, fg=FG_HINT, font=("Consolas", 8)).pack(anchor="w")
        self.prog_tm = tk.Canvas(ptmf, bg=BG2, height=110,
            highlightthickness=1, highlightbackground=BORDER)
        self.prog_tm.pack(fill="x")
        self.prog_tm.bind("<Motion>",   self._prog_tm_hover)
        self.prog_tm.bind("<Leave>",    self._prog_tm_leave)
        self.prog_tm.bind("<Button-1>", self._prog_tm_click)
        self._prog_tm_rects = []
        self.prog_tm_tip = tk.Label(ptmf, text="", bg=BG3, fg=FG,
            font=FONT_SMALL, padx=10, pady=3, anchor="w")
        self.prog_tm_tip.pack(fill="x", pady=(3, 0))

        tk.Frame(p, bg=BORDER, height=1).pack(fill="x")

        # Programs table
        tf = tk.Frame(p, bg=BG, padx=18, pady=8)
        tf.pack(fill="both", expand=True)
        cols = ("name", "publisher", "version", "size", "date", "location")
        self.prog_tree = ttk.Treeview(tf, columns=cols, show="headings",
                                       selectmode="browse")
        for cid, lbl, w, anc in [
            ("name",      "PROGRAM NAME",     310, "w"),
            ("publisher", "PUBLISHER",        175, "w"),
            ("version",   "VERSION",           85, "w"),
            ("size",      "SIZE",             105, "e"),
            ("date",      "INSTALLED",         95, "center"),
            ("location",  "INSTALL LOCATION", 220, "w"),
        ]:
            self.prog_tree.heading(cid, text=lbl,
                command=lambda c=cid: self._prog_sort(c))
            self.prog_tree.column(cid, width=w, anchor=anc,
                                  stretch=(cid in ("name", "location")))
        pvsb = ttk.Scrollbar(tf, orient="vertical",
                              command=self.prog_tree.yview)
        self.prog_tree.configure(yscrollcommand=pvsb.set)
        pvsb.pack(side="right", fill="y")
        self.prog_tree.pack(fill="both", expand=True)

        self.prog_tree.tag_configure("large",  foreground=RED,
                                     font=("Consolas", 10, "bold"))
        self.prog_tree.tag_configure("medium", foreground=YELLOW)
        self.prog_tree.tag_configure("small",  foreground=FG)
        self.prog_tree.tag_configure("nosize", foreground=FG_HINT)

        self.prog_tree.bind("<<TreeviewSelect>>", self._prog_sel_changed)
        self.prog_tree.bind("<Double-1>",          self._prog_open_loc)
        self.prog_tree.bind("<Button-3>",          self._prog_right_click)

        self.prog_ctx = tk.Menu(self, tearoff=0, bg=BG3, fg=FG,
            activebackground=BORDER, activeforeground=FG, font=FONT_SMALL)
        self.prog_ctx.add_command(label="Uninstall…",
            command=self._uninstall_selected)
        self.prog_ctx.add_separator()
        self.prog_ctx.add_command(label="Open install location",
            command=self._prog_open_loc)
        self.prog_ctx.add_command(label="Copy program name",
            command=self._prog_copy_name)

    # ── Programs logic ────────────────────────────────────────────────────────
    def _load_programs(self):
        if self.prog_scanning: return
        self.prog_scanning = True
        self.programs = []
        self.prog_scan_btn.config(text="⏳  LOADING…", state="disabled")
        self.prog_status.config(text="Reading Windows registry…")
        for iid in self.prog_tree.get_children(): self.prog_tree.delete(iid)
        self._prog_clear_treemap()
        for key in self.prog_stat_labels.values(): key.config(text="—")
        threading.Thread(target=self._prog_thread, daemon=True).start()

    def _prog_thread(self):
        progs = read_installed_programs()
        progs.sort(key=lambda x: x["size"] if x["size"] >= 0 else -1,
                   reverse=True)
        self.programs = progs
        self.after(0, self._prog_done)

    def _prog_done(self):
        self.prog_scanning = False
        self.prog_scan_btn.config(text="🔄  REFRESH", state="normal")
        n = len(self.programs)
        known = [p for p in self.programs if p["size"] >= 0]
        total_known = sum(p["size"] for p in known)
        pubs = len(set(p["publisher"] for p in self.programs if p["publisher"]))
        largest = max(known, key=lambda x: x["size"], default=None)

        self.prog_stat_labels["count"].config(text=str(n))
        self.prog_stat_labels["known"].config(text=fmt_bytes(total_known))
        self.prog_stat_labels["pubs"].config(text=str(pubs))
        if largest:
            nm = largest["name"]
            self.prog_stat_labels["largest"].config(
                text=(nm[:20] + "…") if len(nm) > 20 else nm)
        self.prog_status.config(
            text=f"{n} programs found  ·  {len(known)} with known size  "
                 f"·  {fmt_bytes(total_known)} total  "
                 "·  Double-click to open install folder  "
                 "·  Select + click Uninstall to remove")
        self._populate_prog_tree()
        self._draw_prog_treemap()

    def _populate_prog_tree(self, data=None):
        for iid in self.prog_tree.get_children(): self.prog_tree.delete(iid)
        for i, p in enumerate(data or self.programs):
            sz = p["size"]
            if sz >= 1024**3:       tag = "large"
            elif sz >= 200*1024**2: tag = "medium"
            elif sz >= 0:           tag = "small"
            else:                   tag = "nosize"
            self.prog_tree.insert("", "end",
                values=(p["name"], p["publisher"] or "—",
                        p["version"] or "—",
                        fmt_bytes(sz) if sz >= 0 else "unknown",
                        p["install_date"] or "—",
                        p["install_loc"] or "—"),
                tags=(tag,), iid=str(i))

    def _prog_sort(self, col):
        self.prog_sort_rev = (not self.prog_sort_rev
                              if self.prog_sort_col == col else True)
        self.prog_sort_col = col
        keys = {
            "size":      lambda p: p["size"] if p["size"] >= 0 else -1,
            "date":      lambda p: p["install_date"] or "",
            "publisher": lambda p: (p["publisher"] or "").lower(),
            "version":   lambda p: p["version"] or "",
            "location":  lambda p: (p["install_loc"] or "").lower(),
        }
        self.programs.sort(key=keys.get(col, lambda p: p["name"].lower()),
                           reverse=self.prog_sort_rev)
        self._apply_prog_filter()

    def _apply_prog_filter(self):
        q = self.prog_filter_var.get().lower()
        data = [p for p in self.programs
                if q in p["name"].lower()
                or q in (p["publisher"] or "").lower()
                or q in (p["install_loc"] or "").lower()] if q else None
        self._populate_prog_tree(data)

    def _prog_sel_changed(self, _event=None):
        sel = self.prog_tree.selection()
        has_uninstall = False
        if sel:
            try:
                idx = int(sel[0])
                has_uninstall = bool(
                    0 <= idx < len(self.programs)
                    and self.programs[idx].get("uninstall"))
            except (ValueError, IndexError):
                pass
        self.prog_uninstall_btn.config(
            state="normal" if has_uninstall else "disabled")

    def _uninstall_selected(self):
        sel = self.prog_tree.selection()
        if not sel: return
        try:
            idx = int(sel[0])
            prog = self.programs[idx]
        except (ValueError, IndexError):
            return
        if not prog.get("uninstall"):
            messagebox.showinfo("No Uninstaller",
                f"No uninstall command found for:\n{prog['name']}"); return
        if messagebox.askyesno("Uninstall Program",
            f"Launch the uninstaller for:\n\n  {prog['name']}\n\n"
            "Windows will open the program's own uninstaller. Continue?",
            icon="warning"):
            try:
                subprocess.Popen(prog["uninstall"], shell=True)
            except Exception as e:
                messagebox.showerror("Error",
                    f"Could not launch uninstaller:\n{e}")

    def _prog_open_loc(self, _event=None):
        sel = self.prog_tree.selection()
        if not sel: return
        try:
            idx = int(sel[0]); loc = self.programs[idx].get("install_loc", "")
        except (ValueError, IndexError):
            return
        if loc and os.path.isdir(loc):
            open_in_explorer(loc)
        else:
            messagebox.showinfo("Not Found",
                "Install location not recorded or folder doesn't exist.")

    def _prog_copy_name(self):
        sel = self.prog_tree.selection()
        if sel:
            try:
                idx = int(sel[0])
                self.clipboard_clear()
                self.clipboard_append(self.programs[idx]["name"])
            except (ValueError, IndexError):
                pass

    def _prog_right_click(self, event):
        row = self.prog_tree.identify_row(event.y)
        if row:
            self.prog_tree.selection_set(row)
            self._prog_sel_changed()
            self.prog_ctx.post(event.x_root, event.y_root)

    # ── Programs treemap ──────────────────────────────────────────────────────
    def _prog_clear_treemap(self):
        self.prog_tm.delete("all"); self._prog_tm_rects = []

    def _draw_prog_treemap(self):
        self._prog_clear_treemap()
        self.prog_tm.update_idletasks()
        W, H = self.prog_tm.winfo_width(), self.prog_tm.winfo_height()
        if W < 10 or H < 10: return
        known = [(p["name"], p["size"]) for p in self.programs if p["size"] > 0]
        if not known: return
        layout = squarify(known, 2, 2, W - 4, H - 4)
        colors = BAR_COLORS
        clookup = {p["name"]: colors[i % len(colors)]
                   for i, p in enumerate(self.programs)}
        plookup = {p["name"]: p for p in self.programs}
        for name, rx, ry, rw, rh in layout:
            prog = plookup.get(name)
            if not prog: continue
            c = clookup.get(name, BLUE)
            rid = self.prog_tm.create_rectangle(rx, ry, rx+rw, ry+rh,
                fill=_darken(c, 0.2), outline=c, width=1)
            tid = None
            if rw > 60 and rh > 20:
                label = name if rw > 120 else name[:max(4, int(rw/8))]
                tid = self.prog_tm.create_text(rx+rw/2, ry+rh/2,
                    text=f"{label}\n{fmt_bytes(prog['size'])}",
                    fill=FG, font=("Consolas", 8),
                    justify="center", width=rw-4)
            self._prog_tm_rects.append(
                (rid, tid, prog, rx, ry, rx+rw, ry+rh, c))

    def _prog_tm_find(self, x, y):
        for rid, tid, p, x1, y1, x2, y2, c in self._prog_tm_rects:
            if x1 <= x <= x2 and y1 <= y <= y2: return rid, p, c
        return None, None, None

    def _prog_tm_hover(self, event):
        rid, p, c = self._prog_tm_find(event.x, event.y)
        if p:
            self.prog_tm_tip.config(
                text=f"  {p['name']}   ·   {fmt_bytes(p['size'])}"
                     f"   ·   {p['publisher'] or '—'}"
                     f"   ·   v{p['version'] or '—'}",
                fg=c or FG)
            if rid != self._prog_hovered_tm:
                if self._prog_hovered_tm:
                    self.prog_tm.itemconfig(self._prog_hovered_tm, width=1)
                self.prog_tm.itemconfig(rid, width=2)
                self._prog_hovered_tm = rid
        else:
            self.prog_tm_tip.config(text="")

    def _prog_tm_leave(self, _event):
        self.prog_tm_tip.config(text="")
        if self._prog_hovered_tm:
            self.prog_tm.itemconfig(self._prog_hovered_tm, width=1)
            self._prog_hovered_tm = None

    def _prog_tm_click(self, event):
        _, p, _ = self._prog_tm_find(event.x, event.y)
        if p:
            for i, prog in enumerate(self.programs):
                if prog["name"] == p["name"]:
                    try:
                        iid = str(i)
                        self.prog_tree.selection_set(iid)
                        self.prog_tree.see(iid)
                        self._prog_sel_changed()
                    except Exception:
                        pass
                    break


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = DiskAnalyzer()
    app.mainloop()
