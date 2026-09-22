import logging
import msvcrt
import queue
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

from actions import archive_file, delete_file
from applog import setup_logging
from icon import app_icon
from scanner import (
    human_size,
    load_config,
    load_keep_list,
    mark_kept,
    save_keep_list,
    scan,
    total_size,
)
from PIL import ImageTk

APP_DIR = Path(__file__).parent
LOCK_PATH = APP_DIR / ".instance.lock"
_lock_file = None
log = logging.getLogger("space-cleanup")


def _acquire_single_instance_lock():
    """Best-effort single-instance guard via an exclusive OS file lock (stdlib
    msvcrt, Windows-only, no extra dependency). Held for the process's lifetime."""
    global _lock_file
    f = open(LOCK_PATH, "a+b")
    if f.tell() == 0:
        f.write(b"0")
        f.flush()
    f.seek(0)
    try:
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        # Expected when another instance holds the lock: report "already running".
        f.close()
        return False
    _lock_file = f
    return True

INK = "#12131C"
PANEL = "#1B1D2B"
PANEL_HOVER = "#242640"
HAIRLINE = "#2E3044"
TEXT = "#EDEEF7"
MUTED = "#8688A6"
ACCENT = "#F5A623"
DANGER = "#F0576B"
SELECTED_ROW = "#3A2F14"


def _pick_mono_font():
    families = set(tkfont.families())
    for name in ("Cascadia Mono", "Cascadia Code", "Consolas"):
        if name in families:
            return name
    return "Consolas"


def _setup_styles(root, mono):
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(
        "Dark.Treeview",
        background=PANEL,
        fieldbackground=PANEL,
        foreground=TEXT,
        bordercolor=HAIRLINE,
        rowheight=26,
        borderwidth=0,
        font=("Segoe UI", 9),
    )
    style.map("Dark.Treeview", background=[("selected", SELECTED_ROW)], foreground=[("selected", TEXT)])
    style.configure(
        "Dark.Treeview.Heading",
        background=INK,
        foreground=MUTED,
        bordercolor=HAIRLINE,
        relief="flat",
        font=(mono, 9, "bold"),
    )
    style.map("Dark.Treeview.Heading", background=[("active", PANEL)], foreground=[("active", ACCENT)])
    style.configure("Dark.Vertical.TScrollbar", background=PANEL, troughcolor=INK, bordercolor=INK, arrowcolor=MUTED)


class SpaceCleanupApp:
    def __init__(self):
        self.config = load_config()
        self.keep_list = load_keep_list()
        self.candidates = []
        self._by_path = {}
        self._sort_state = {}
        self._scan_generation = 0

        self.root = tk.Tk()
        self.root.title("Space Cleanup Assistant")
        self.root.configure(bg=INK)
        self.root.geometry("980x560")
        self._mono = _pick_mono_font()
        self._icon_photo = ImageTk.PhotoImage(app_icon())
        self.root.iconphoto(True, self._icon_photo)
        _setup_styles(self.root, self._mono)

        # The scan runs on a worker thread; it must never touch Tk directly, so it
        # posts a callable here and this drain (always running on the Tk thread via
        # after()) is what actually applies the result.
        self._ui_queue = queue.Queue()
        self.root.after(50, self._drain_ui_queue)

        self._build_ui()
        self.rescan()

    def _drain_ui_queue(self):
        try:
            while True:
                fn = self._ui_queue.get_nowait()
                fn()
        except queue.Empty:
            pass
        self.root.after(50, self._drain_ui_queue)

    def _post(self, fn):
        self._ui_queue.put(fn)

    def _build_ui(self):
        tk.Frame(self.root, bg=ACCENT, height=2).pack(fill="x")

        top = tk.Frame(self.root, bg=INK)
        top.pack(fill="x", padx=14, pady=(10, 8))

        tk.Label(top, text="SPACE CLEANUP", bg=INK, fg=ACCENT, font=(self._mono, 10, "bold")).pack(side="left")

        self.rescan_btn = self._make_button(top, "↻ rescan", self.rescan)
        self.rescan_btn.pack(side="right")

        status_row = tk.Frame(self.root, bg=INK)
        status_row.pack(fill="x", padx=14, pady=(0, 6))
        self.status_label = tk.Label(status_row, text="Scanning...", bg=INK, fg=MUTED, font=(self._mono, 9))
        self.status_label.pack(side="left")

        tree_frame = tk.Frame(self.root, bg=INK)
        tree_frame.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        cols = ("name", "size", "modified", "accessed", "reason", "path")
        self.tree = ttk.Treeview(
            tree_frame, columns=cols, show="headings", selectmode="extended", style="Dark.Treeview"
        )
        headings = {
            "name": ("Name", 220),
            "size": ("Size", 90),
            "modified": ("Last Modified", 120),
            "accessed": ("Last Accessed", 120),
            "reason": ("Reason", 100),
            "path": ("Path", 320),
        }
        for c, (label, width) in headings.items():
            self.tree.heading(c, text=label, command=lambda c=c: self._sort_by(c))
            self.tree.column(c, width=width, anchor="w")

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview, style="Dark.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)

        btns = tk.Frame(self.root, bg=INK)
        btns.pack(fill="x", padx=10, pady=(0, 12))
        self._make_button(btns, "keep", self.keep_selected).pack(side="left", padx=4)
        self._make_button(btns, "archive", self.archive_selected, accent=ACCENT).pack(side="left", padx=4)
        self._make_button(btns, "delete → recycle bin", self.delete_selected, accent=DANGER).pack(
            side="left", padx=4
        )
        tk.Label(
            btns, text="ctrl/shift-click for multiple", bg=INK, fg=MUTED, font=(self._mono, 8)
        ).pack(side="right", padx=6)

    def _make_button(self, parent, text, command, accent=None):
        fg = accent or TEXT
        btn = tk.Button(
            parent,
            text=text,
            command=command,
            bg=PANEL,
            fg=fg,
            activebackground=PANEL_HOVER,
            activeforeground=fg,
            font=(self._mono, 9, "bold"),
            relief="flat",
            bd=0,
            padx=14,
            pady=7,
            cursor="hand2",
            highlightthickness=1,
            highlightbackground=HAIRLINE,
            highlightcolor=HAIRLINE,
        )
        btn.bind("<Enter>", lambda e: btn.config(bg=PANEL_HOVER))
        btn.bind("<Leave>", lambda e: btn.config(bg=PANEL))
        return btn

    def rescan(self):
        self._scan_generation += 1
        generation = self._scan_generation

        self.status_label.config(text="Scanning...")
        self.rescan_btn.config(state="disabled")
        self.tree.delete(*self.tree.get_children())

        def worker():
            candidates = scan(self.config, self.keep_list)

            def apply():
                # Drop results from a stale rescan superseded by a newer one.
                if generation == self._scan_generation:
                    self._on_scanned(candidates)
                self.rescan_btn.config(state="normal")

            self._post(apply)

        threading.Thread(target=worker, daemon=True).start()

    def _on_scanned(self, candidates):
        self.candidates = candidates
        self._by_path = {str(c["path"]): c for c in candidates}
        self.populate()

    def populate(self):
        self.tree.delete(*self.tree.get_children())
        for c in self.candidates:
            reason = "Large+Stale" if c["is_large"] and c["is_stale"] else ("Large" if c["is_large"] else "Stale")
            modified = datetime.fromtimestamp(c["mtime"]).strftime("%Y-%m-%d")
            accessed = datetime.fromtimestamp(c["atime"]).strftime("%Y-%m-%d")
            self.tree.insert(
                "",
                "end",
                iid=str(c["path"]),
                values=(c["name"], human_size(c["size"]), modified, accessed, reason, str(c["path"])),
            )
        self._update_status()

    def _update_status(self):
        total = total_size(self.candidates)
        self.status_label.config(
            text=(
                f"{len(self.candidates)} candidate file(s) - {human_size(total)} total  "
                f"(large ≥ {self.config['large_file_mb']} MB or untouched ≥ {self.config['stale_days']} days)"
            )
        )

    def _selected_candidates(self):
        sel = self.tree.selection()
        return [self._by_path[s] for s in sel if s in self._by_path]

    def _remove_row(self, c):
        path_str = str(c["path"])
        if self.tree.exists(path_str):
            self.tree.delete(path_str)
        self._by_path.pop(path_str, None)
        if c in self.candidates:
            self.candidates.remove(c)
        self._update_status()

    def keep_selected(self):
        items = self._selected_candidates()
        if not items:
            return
        for c in items:
            mark_kept(self.keep_list, c["path"], c["size"], c["mtime"], c["atime"])
            self._remove_row(c)
        save_keep_list(self.keep_list)

    def archive_selected(self):
        items = self._selected_candidates()
        if not items:
            return
        errors = []
        for c in items:
            try:
                archive_file(c["path"], c["root"])
                self._remove_row(c)
            except Exception as e:  # broad on purpose: per-file failure is shown to the user; keep going with the rest
                log.warning("archive failed for %s", c["path"], exc_info=True)
                errors.append(f"{c['name']}: {e}")
        if errors:
            messagebox.showerror("Archive errors", "\n".join(errors))

    def delete_selected(self):
        items = self._selected_candidates()
        if not items:
            return
        names = "\n".join(c["name"] for c in items[:10])
        more = "" if len(items) <= 10 else f"\n...and {len(items) - 10} more"
        if not messagebox.askyesno(
            "Confirm delete",
            f"Send {len(items)} file(s) to the Recycle Bin?\n\n{names}{more}",
        ):
            return
        errors = []
        for c in items:
            try:
                delete_file(c["path"])
                self._remove_row(c)
            except Exception as e:  # broad on purpose: per-file failure is shown to the user; keep going with the rest
                log.warning("delete (recycle bin) failed for %s", c["path"], exc_info=True)
                errors.append(f"{c['name']}: {e}")
        if errors:
            messagebox.showerror("Delete errors", "\n".join(errors))

    def _sort_by(self, col):
        reverse = self._sort_state.get(col, False)

        def keyfunc(item_id):
            # Size needs the raw byte count (the displayed "1.2 MB" string doesn't
            # sort correctly as text); every other column sorts fine on its
            # displayed text (dates are ISO-formatted so they sort correctly too).
            if col == "size":
                c = self._by_path.get(item_id)
                return c["size"] if c else 0
            return self.tree.set(item_id, col).lower()

        items = list(self.tree.get_children(""))
        items.sort(key=keyfunc, reverse=reverse)
        for idx, k in enumerate(items):
            self.tree.move(k, "", idx)
        self._sort_state[col] = not reverse

    def run(self):
        self.root.mainloop()


def main():
    setup_logging("space-cleanup")
    if not _acquire_single_instance_lock():
        print("Space Cleanup is already running in another window.")
        return
    app = SpaceCleanupApp()
    app.run()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback

        log.exception("fatal error")

        with open(APP_DIR / "app_error.log", "a", encoding="utf-8") as f:
            f.write(f"\n--- {time.ctime()} ---\n")
            f.write(traceback.format_exc())
        raise
