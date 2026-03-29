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
import sys
import shutil
import subprocess
from pathlib import Path
import time


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
ACCENT    = RED

TYPE_COLOR = {
    "System":   "#FF4136",
    "Apps":     "#00B4D8",
    "User":     "#2ECC40",
    "Cache":    "#FFDC00",
    "Other":    "#888888",
}

BAR_COLORS = [RED, BLUE, GREEN, YELLOW, PURPLE,
              "#FF851B", "#FF6B9D", "#01FFE4", "#F5A623", "#A8E6CF"]

FONT_MONO  = ("Consolas", 10)
FONT_SMALL = ("Consolas", 9)
FONT_BIG   = ("Consolas", 14, "bold")
FONT_HEAD  = ("Consolas", 9, "bold")


# ── Helpers ──────────────────────────────────────────────────────────────────
def fmt_bytes(b):
    if b is None: return "—"
    for unit in ("B","KB","MB","GB","TB"):
        if b < 1024: return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.2f} PB"

def get_folder_size(path):
    """Return (total_bytes, file_count) for a directory tree."""
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
    if n in ("windows", "winnt"):                return "System"
    if n in ("pagefile.sys","hiberfil.sys","swapfile.sys","$recycle.bin",
             "$winreagent","system volume information","recovery","boot"): return "System"
    if "program files" in n:                      return "Apps"
    if "programdata" in n:                        return "Apps"
    if "appdata\\local" in p or "appdata/local" in p: return "Cache"
    if "appdata\\roaming" in p or "appdata/roaming" in p: return "Cache"
    if "cache" in n:                              return "Cache"
    if "users" in n:                              return "User"
    return "Other"

def open_in_explorer(path):
    try:
        subprocess.Popen(["explorer", path])
    except Exception:
        pass


# ── Canvas treemap ────────────────────────────────────────────────────────────
def squarify(items, x, y, w, h):
    """Very small squarify-style layout returning list of (item, rx,ry,rw,rh)."""
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
                rw = w; rh = frac * h
                result.append((name, x, pos, rw, rh))
                pos += rh
            else:
                rh = h; rw = frac * w
                result.append((name, pos, y, rw, rh))
                pos += rw

    while remaining:
        if w >= h:
            row_w = w * remaining[0][1] / total if total else w
            row, rest, used = [], [], 0
            for item in remaining:
                frac = item[1] / total
                if used + frac <= remaining[0][1] / total * (w / h) + 1e-9 or not row:
                    row.append(item); used += frac
                else:
                    rest.append(item)
            if not rest:
                layout_row(row, x, y, w, h, False)
                break
            row_h = used * h
            layout_row(row, x, y, w, row_h, False)
            y += row_h; h -= row_h; total -= sum(s for _, s in row)
            remaining = rest
        else:
            row_h = h * remaining[0][1] / total if total else h
            row, rest, used = [], [], 0
            for item in remaining:
                frac = item[1] / total
                if used + frac <= remaining[0][1] / total * (h / w) + 1e-9 or not row:
                    row.append(item); used += frac
                else:
                    rest.append(item)
            if not rest:
                layout_row(row, x, y, w, h, True)
                break
            row_w = used * w
            layout_row(row, x, y, row_w, h, True)
            x += row_w; w -= row_w; total -= sum(s for _, s in row)
            remaining = rest
    return result


# ── Main App ──────────────────────────────────────────────────────────────────
class DiskAnalyzer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("DiskAnalyzer")
        self.geometry("1100x780")
        self.minsize(800, 600)
        self.configure(bg=BG)
        self._set_icon()

        self.scan_root   = tk.StringVar(value="C:\\")
        self.results     = []          # list of dicts
        self.scanning    = False
        self.total_disk  = 0
        self.used_disk   = 0
        self.free_disk   = 0
        self._abort      = threading.Event()
        self._sort_col   = "size"
        self._sort_rev   = True
        self._hovered_tm = None

        self._build_ui()
        self._style_ttk()

    # ── icon (draws a tiny coloured square if no .ico available) ─────────────
    def _set_icon(self):
        try:
            img = tk.PhotoImage(width=16, height=16)
            img.put(RED, to=(0,0,15,15))
            self.iconphoto(True, img)
        except Exception:
            pass

    # ── TTK style ─────────────────────────────────────────────────────────────
    def _style_ttk(self):
        s = ttk.Style(self)
        s.theme_use("default")
        s.configure("Treeview",
            background=BG2, foreground=FG, fieldbackground=BG2,
            borderwidth=0, rowheight=24, font=FONT_MONO)
        s.configure("Treeview.Heading",
            background=BG3, foreground=FG_DIM, relief="flat",
            font=FONT_HEAD)
        s.map("Treeview",
            background=[("selected", BG3)],
            foreground=[("selected", FG)])
        s.map("Treeview.Heading",
            background=[("active", BORDER)])
        s.configure("Vertical.TScrollbar",
            background=BG3, troughcolor=BG, borderwidth=0, arrowcolor=FG_DIM)
        s.configure("TProgressbar",
            troughcolor=BG3, background=GREEN, borderwidth=0)

    # ── UI construction ────────────────────────────────────────────────────────
    def _build_ui(self):
        # ── top bar ──
        top = tk.Frame(self, bg=BG, pady=12, padx=18)
        top.pack(fill="x")

        tk.Label(top, text="DISK ANALYZER", bg=BG, fg=FG,
                 font=("Consolas", 16, "bold")).pack(side="left")

        btn_frame = tk.Frame(top, bg=BG)
        btn_frame.pack(side="right")

        tk.Label(btn_frame, text="Drive:", bg=BG, fg=FG_DIM,
                 font=FONT_SMALL).pack(side="left", padx=(0,4))
        self.drive_entry = tk.Entry(btn_frame, textvariable=self.scan_root,
            width=12, bg=BG3, fg=FG, insertbackground=FG,
            relief="flat", font=FONT_MONO, highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=ACCENT)
        self.drive_entry.pack(side="left", padx=(0,8))

        tk.Button(btn_frame, text="Browse…", command=self._browse,
            bg=BG3, fg=FG_DIM, relief="flat", font=FONT_SMALL,
            activebackground=BORDER, activeforeground=FG,
            padx=8, pady=4, cursor="hand2").pack(side="left", padx=(0,8))

        self.scan_btn = tk.Button(btn_frame, text="▶  SCAN",
            command=self._toggle_scan,
            bg=ACCENT, fg="#fff", relief="flat", font=("Consolas",11,"bold"),
            activebackground="#cc3329", activeforeground="#fff",
            padx=16, pady=6, cursor="hand2")
        self.scan_btn.pack(side="left")

        # ── separator ──
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        # ── stats row ──
        self.stats_frame = tk.Frame(self, bg=BG, pady=10, padx=18)
        self.stats_frame.pack(fill="x")
        self.stat_labels = {}
        for key, label, color in [
            ("path",  "PATH",     FG_DIM),
            ("total", "TOTAL",    FG_DIM),
            ("used",  "USED",     RED),
            ("free",  "FREE",     GREEN),
            ("pct",   "% USED",   YELLOW),
        ]:
            f = tk.Frame(self.stats_frame, bg=BG)
            f.pack(side="left", padx=(0,32))
            tk.Label(f, text=label, bg=BG, fg=FG_HINT,
                     font=("Consolas",8)).pack(anchor="w")
            lbl = tk.Label(f, text="—", bg=BG, fg=color, font=("Consolas",13,"bold"))
            lbl.pack(anchor="w")
            self.stat_labels[key] = lbl

        # ── progress bar + status ──
        prog_frame = tk.Frame(self, bg=BG, padx=18)
        prog_frame.pack(fill="x", pady=(0,6))
        self.progress = ttk.Progressbar(prog_frame, mode="determinate",
                                        style="TProgressbar")
        self.progress.pack(fill="x", pady=(0,4))
        self.status_var = tk.StringVar(value="Ready. Enter a drive path and press SCAN.")
        tk.Label(prog_frame, textvariable=self.status_var, bg=BG, fg=FG_DIM,
                 font=FONT_SMALL, anchor="w").pack(fill="x")

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        # ── treemap canvas ──
        tm_frame = tk.Frame(self, bg=BG, padx=18, pady=10)
        tm_frame.pack(fill="x")
        tk.Label(tm_frame, text="SPACE MAP", bg=BG, fg=FG_HINT,
                 font=("Consolas",8)).pack(anchor="w")
        self.tm_canvas = tk.Canvas(tm_frame, bg=BG2, height=130,
            highlightthickness=1, highlightbackground=BORDER)
        self.tm_canvas.pack(fill="x")
        self.tm_canvas.bind("<Motion>", self._tm_hover)
        self.tm_canvas.bind("<Leave>",  self._tm_leave)
        self.tm_canvas.bind("<Button-1>", self._tm_click)
        self._tm_rects = []   # (rect_id, text_id, item_dict)
        self.tm_tip = tk.Label(tm_frame, text="", bg=BG3, fg=FG,
            font=FONT_SMALL, padx=10, pady=4, anchor="w")
        self.tm_tip.pack(fill="x", pady=(4,0))

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        # ── treeview table ──
        tree_outer = tk.Frame(self, bg=BG, padx=18, pady=10)
        tree_outer.pack(fill="both", expand=True)

        header = tk.Frame(tree_outer, bg=BG)
        header.pack(fill="x", pady=(0,6))
        tk.Label(header, text="DIRECTORY BREAKDOWN", bg=BG, fg=FG_HINT,
                 font=("Consolas",8)).pack(side="left")

        # quick-filter
        tk.Label(header, text="Filter:", bg=BG, fg=FG_DIM,
                 font=FONT_SMALL).pack(side="right", padx=(8,0))
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *_: self._apply_filter())
        fe = tk.Entry(header, textvariable=self.filter_var, width=18,
            bg=BG3, fg=FG, insertbackground=FG, relief="flat",
            font=FONT_MONO, highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=BLUE)
        fe.pack(side="right")

        cols = ("path", "size", "pct", "items", "type")
        self.tree = ttk.Treeview(tree_outer, columns=cols, show="headings",
                                  selectmode="browse")

        col_cfg = [
            ("path",  "PATH",    480, "w"),
            ("size",  "SIZE",    100, "e"),
            ("pct",   "% OF USED", 90,"e"),
            ("items", "ITEMS",    90, "e"),
            ("type",  "TYPE",     80, "center"),
        ]
        for cid, label, width, anchor in col_cfg:
            self.tree.heading(cid, text=label,
                command=lambda c=cid: self._sort(c))
            self.tree.column(cid, width=width, anchor=anchor, stretch=(cid=="path"))

        vsb = ttk.Scrollbar(tree_outer, orient="vertical",
                             command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)

        self.tree.bind("<Double-1>",     self._open_selected)
        self.tree.bind("<Button-3>",     self._right_click)
        self.tree.tag_configure("System", foreground=TYPE_COLOR["System"])
        self.tree.tag_configure("Apps",   foreground=TYPE_COLOR["Apps"])
        self.tree.tag_configure("User",   foreground=TYPE_COLOR["User"])
        self.tree.tag_configure("Cache",  foreground=TYPE_COLOR["Cache"])
        self.tree.tag_configure("Other",  foreground=TYPE_COLOR["Other"])
        self.tree.tag_configure("big",    font=("Consolas",10,"bold"))

        # context menu
        self.ctx_menu = tk.Menu(self, tearoff=0, bg=BG3, fg=FG,
            activebackground=BORDER, activeforeground=FG, font=FONT_SMALL)
        self.ctx_menu.add_command(label="Open in Explorer",
            command=self._open_selected)
        self.ctx_menu.add_command(label="Copy path",
            command=self._copy_path)

        # ── bottom bar ──
        bottom = tk.Frame(self, bg=BG3, pady=6, padx=18)
        bottom.pack(fill="x", side="bottom")
        self.bottom_lbl = tk.Label(bottom,
            text="Double-click a row to open in Explorer  •  Right-click for options",
            bg=BG3, fg=FG_HINT, font=FONT_SMALL)
        self.bottom_lbl.pack(side="left")
        tk.Label(bottom, text="DiskAnalyzer — python disk_analyzer.py",
            bg=BG3, fg=FG_HINT, font=FONT_SMALL).pack(side="right")

    # ── browse ────────────────────────────────────────────────────────────────
    def _browse(self):
        d = filedialog.askdirectory(initialdir=self.scan_root.get())
        if d:
            self.scan_root.set(d)

    # ── scan toggle ──────────────────────────────────────────────────────────
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
            messagebox.showerror("Invalid path", f"Cannot find directory:\n{root_path}")
            return

        self._abort.clear()
        self.results = []
        self.scanning = True
        self.scan_btn.config(text="■  STOP", bg="#555")
        self.progress["value"] = 0
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self._clear_treemap()
        self.tm_tip.config(text="")
        self.status_var.set(f"Scanning {root_path} …")

        # drive stats
        try:
            usage = shutil.disk_usage(root_path)
            self.total_disk = usage.total
            self.used_disk  = usage.used
            self.free_disk  = usage.free
        except Exception:
            self.total_disk = self.used_disk = self.free_disk = 0

        self._update_stats(root_path)
        threading.Thread(target=self._scan_thread,
                         args=(root_path,), daemon=True).start()

    # ── background scan ───────────────────────────────────────────────────────
    def _scan_thread(self, root_path):
        items = []
        try:
            entries = list(os.scandir(root_path))
        except PermissionError:
            self.after(0, lambda: self.status_var.set("Permission denied on root."))
            self.after(0, self._scan_done)
            return

        total = len(entries)
        for idx, entry in enumerate(entries):
            if self._abort.is_set():
                break
            pct = int((idx / max(total,1)) * 100)
            self.after(0, lambda p=pct, n=entry.name:
                self.status_var.set(f"Scanning {n}…  ({p}%)"))
            self.after(0, lambda p=pct: self.progress.configure(value=p))

            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    size, count = get_folder_size(entry.path)
                    type_ = classify(entry.name, entry.path)
                    items.append({
                        "name":  entry.name,
                        "path":  entry.path,
                        "size":  size,
                        "items": count,
                        "type":  type_,
                        "is_file": False,
                    })
                else:
                    st = entry.stat(follow_symlinks=False)
                    type_ = classify(entry.name, entry.path)
                    items.append({
                        "name":  entry.name,
                        "path":  entry.path,
                        "size":  st.st_size,
                        "items": 1,
                        "type":  type_,
                        "is_file": True,
                    })
            except (PermissionError, OSError):
                pass

        self.results = sorted(items, key=lambda x: x["size"], reverse=True)
        self.after(0, self._scan_done)

    def _scan_done(self):
        self.scanning = False
        self.scan_btn.config(text="▶  SCAN", bg=ACCENT)
        self.progress["value"] = 100
        n = len(self.results)
        total_items = sum(r["items"] for r in self.results)
        self.status_var.set(
            f"Done — {n} entries · {total_items:,} total files · "
            f"Double-click to open in Explorer")
        self._populate_tree()
        self._draw_treemap()

    # ── stats row ────────────────────────────────────────────────────────────
    def _update_stats(self, path):
        pct = (self.used_disk / self.total_disk * 100) if self.total_disk else 0
        self.stat_labels["path"].config(text=path)
        self.stat_labels["total"].config(text=fmt_bytes(self.total_disk))
        self.stat_labels["used"].config(text=fmt_bytes(self.used_disk))
        self.stat_labels["free"].config(text=fmt_bytes(self.free_disk))
        self.stat_labels["pct"].config(text=f"{pct:.1f}%")

    # ── treeview ─────────────────────────────────────────────────────────────
    def _populate_tree(self, data=None):
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        rows = data if data is not None else self.results
        for r in rows:
            pct = (r["size"] / self.used_disk * 100) if self.used_disk else 0
            tags = [r["type"]]
            if r["size"] > 5 * 1024**3:   # >5 GB bold
                tags.append("big")
            self.tree.insert("", "end",
                values=(
                    r["path"],
                    fmt_bytes(r["size"]),
                    f"{pct:.1f}%",
                    f'{r["items"]:,}',
                    r["type"],
                ),
                tags=tags,
                iid=r["path"],
            )

    def _sort(self, col):
        if self._sort_col == col:
            self._sort_rev = not self._sort_rev
        else:
            self._sort_col = col
            self._sort_rev = True

        def key(r):
            if col == "size":  return r["size"]
            if col == "items": return r["items"]
            if col == "type":  return r["type"]
            if col == "pct":   return r["size"]
            return r["path"].lower()

        self.results.sort(key=key, reverse=self._sort_rev)
        self._apply_filter()

    def _apply_filter(self):
        q = self.filter_var.get().lower()
        filtered = [r for r in self.results
                    if q in r["path"].lower() or q in r["type"].lower()] if q else self.results
        self._populate_tree(filtered)

    def _open_selected(self, event=None):
        sel = self.tree.selection()
        if sel:
            open_in_explorer(sel[0])

    def _copy_path(self):
        sel = self.tree.selection()
        if sel:
            self.clipboard_clear()
            self.clipboard_append(sel[0])

    def _right_click(self, event):
        row = self.tree.identify_row(event.y)
        if row:
            self.tree.selection_set(row)
            self.ctx_menu.post(event.x_root, event.y_root)

    # ── treemap ───────────────────────────────────────────────────────────────
    def _clear_treemap(self):
        self.tm_canvas.delete("all")
        self._tm_rects = []

    def _draw_treemap(self):
        self._clear_treemap()
        if not self.results:
            return
        self.tm_canvas.update_idletasks()
        W = self.tm_canvas.winfo_width()
        H = self.tm_canvas.winfo_height()
        if W < 10 or H < 10:
            return

        items = [(r["path"], r["size"]) for r in self.results if r["size"] > 0]
        layout = squarify(items, 2, 2, W-4, H-4)

        lookup = {r["path"]: r for r in self.results}
        color_map = {}
        ci = 0
        for r in self.results:
            color_map[r["path"]] = BAR_COLORS[ci % len(BAR_COLORS)]
            ci += 1

        for (path, rx, ry, rw, rh) in layout:
            r = lookup.get(path)
            if not r: continue
            c = TYPE_COLOR.get(r["type"], "#888")
            rid = self.tm_canvas.create_rectangle(
                rx, ry, rx+rw, ry+rh,
                fill=_darken(c, 0.15), outline=c, width=1)
            tid = None
            if rw > 50 and rh > 22:
                label = r["name"] if rw > 80 else r["name"][:int(rw/7)]
                tid = self.tm_canvas.create_text(
                    rx+rw/2, ry+rh/2,
                    text=f"{label}\n{fmt_bytes(r['size'])}",
                    fill=FG, font=("Consolas", 8), justify="center",
                    width=rw-4)
            self._tm_rects.append((rid, tid, r, rx, ry, rx+rw, ry+rh))

    def _tm_find(self, x, y):
        for (rid, tid, r, x1, y1, x2, y2) in self._tm_rects:
            if x1 <= x <= x2 and y1 <= y <= y2:
                return rid, r
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

    def _tm_leave(self, event):
        self.tm_tip.config(text="")
        if self._hovered_tm:
            self.tm_canvas.itemconfig(self._hovered_tm, width=1)
            self._hovered_tm = None

    def _tm_click(self, event):
        _, r = self._tm_find(event.x, event.y)
        if r:
            self.tree.selection_set(r["path"])
            self.tree.see(r["path"])


def _darken(hex_color, amount=0.3):
    """Return a darkened version of a #RRGGBB colour."""
    h = hex_color.lstrip("#")
    rgb = tuple(int(h[i:i+2], 16) for i in (0,2,4))
    rgb = tuple(max(0, int(c * (1 - amount))) for c in rgb)
    return "#{:02x}{:02x}{:02x}".format(*rgb)


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = DiskAnalyzer()
    app.mainloop()
