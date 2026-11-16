"""Screen 4: Results - All files / Duplicate files / Large files."""
import os
import tkinter as tk
from tkinter import messagebox, ttk

from analytics.analytics import filter_large, filter_pdfs, sort_by_name, sort_by_size, total_reclaimable, total_size
from scanner.duplicate_finder import DuplicateDetector
from ui import BasePage, clear_tree, create_tree
from utils.formatting import format_size, format_timestamp, short_hash

FILE_COLUMNS = [("name", "File name", 220), ("path", "Full path", 420), ("size", "Size", 90),
                ("modified", "Modified", 140), ("status", "Status", 80)]
DUP_COLUMNS = [("group", "Group", 60), ("name", "File name", 200), ("path", "Full path", 380),
               ("size", "Size", 90), ("hash", "SHA-256", 120)]


class ResultsPage(BasePage):
    title = "Results"

    def __init__(self, parent, app) -> None:
        super().__init__(parent, app)
        self.files = []
        self.dup_by_iid = {}
        self.group_sizes = {}
        self.scan_choices = {}

        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 8))
        ttk.Label(bar, text="Scan:").pack(side="left")
        self.scan_combo = ttk.Combobox(bar, state="readonly", width=60)
        self.scan_combo.pack(side="left", padx=6)
        self.scan_combo.bind("<<ComboboxSelected>>", lambda e: self._load_selected())
        ttk.Label(bar, text="Large file threshold (MB):").pack(side="left", padx=(16, 4))
        self.large_var = tk.StringVar(value="100")
        ttk.Entry(bar, textvariable=self.large_var, width=6).pack(side="left")
        ttk.Button(bar, text="Apply", command=self._fill_large).pack(side="left", padx=6)
        self.summary_var = tk.StringVar()
        ttk.Label(self, textvariable=self.summary_var, style="Muted.TLabel").pack(anchor="w", pady=(0, 6))

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)
        all_tab, dup_tab, large_tab = ttk.Frame(notebook), ttk.Frame(notebook), ttk.Frame(notebook)
        notebook.add(all_tab, text="All Files")
        notebook.add(dup_tab, text="Duplicate Files")
        notebook.add(large_tab, text="Large Files")

        opts = ttk.Frame(all_tab)
        opts.pack(fill="x", pady=4)
        self.pdf_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts, text="PDF files only", variable=self.pdf_var, command=self._fill_all).pack(side="left")
        self.sort_var = tk.StringVar(value="Size (largest first)")
        sorter = ttk.Combobox(opts, textvariable=self.sort_var, state="readonly", width=22,
                              values=["Size (largest first)", "Size (smallest first)", "Name (A-Z)"])
        sorter.pack(side="left", padx=12)
        sorter.bind("<<ComboboxSelected>>", lambda e: self._fill_all())
        self.all_tree = create_tree(all_tab, FILE_COLUMNS)

        ttk.Label(dup_tab, text="Select the copies you want to move to quarantine. Nothing is "
                                "selected automatically, and at least one copy of every group must stay.",
                  style="Muted.TLabel").pack(anchor="w", pady=4)
        self.dup_tree = create_tree(dup_tab, DUP_COLUMNS)
        ttk.Button(dup_tab, text="Quarantine selected copies", style="Danger.TButton",
                   command=self._quarantine_selected).pack(anchor="e", pady=6)
        self.large_tree = create_tree(large_tab, FILE_COLUMNS)

    # ------------------------------------------------------------------ data
    def refresh(self) -> None:
        history = self.run_safely(self.services.scan_repo.get_scan_history, 50) or []
        usable = [s for s in history if s["status"] in ("COMPLETED", "CANCELLED")]
        self.scan_choices = {f"#{s['scan_id']}  {s['root_path']}  ({s['status'].title()})": s["scan_id"]
                             for s in usable}
        self.scan_combo["values"] = list(self.scan_choices.keys())
        current = self.app.current_scan_id
        for label, scan_id in self.scan_choices.items():
            if scan_id == current:
                self.scan_combo.set(label)
                break
        else:
            if self.scan_choices:
                self.scan_combo.set(next(iter(self.scan_choices)))
        self._load_selected()

    def _selected_scan_id(self):
        return self.scan_choices.get(self.scan_combo.get())

    def _load_selected(self) -> None:
        scan_id = self._selected_scan_id()
        if scan_id is None:
            self.files = []
            self.summary_var.set("No finished scan yet - run one from the Scan page.")
        else:
            self.app.current_scan_id = scan_id
            self.files = self.run_safely(self.services.file_repo.get_files, scan_id) or []
            self.summary_var.set(f"{len(self.files):,} files, {format_size(total_size(self.files))} in this scan")
        self._fill_all()
        self._fill_duplicates()
        self._fill_large()

    @staticmethod
    def _file_row(f):
        return (f["file_name"], f["absolute_path"], format_size(f["size_bytes"]),
                format_timestamp(f["modified_at"]), f["scan_status"].title())

    def _fill_all(self) -> None:
        files = filter_pdfs(self.files) if self.pdf_var.get() else self.files
        choice = self.sort_var.get()
        if choice.startswith("Name"):
            files = sort_by_name(files)
        else:
            files = sort_by_size(files, largest_first=choice.endswith("largest first)"))
        clear_tree(self.all_tree)
        for f in files:
            self.all_tree.insert("", "end", values=self._file_row(f))

    def _fill_large(self) -> None:
        try:
            threshold = int(float(self.large_var.get()) * 1024 * 1024)
        except ValueError:
            messagebox.showwarning("FileSense", "Enter the size threshold as a number of MB.")
            return
        clear_tree(self.large_tree)
        for f in sort_by_size(filter_large(self.files, threshold)):
            self.large_tree.insert("", "end", values=self._file_row(f))

    def _fill_duplicates(self) -> None:
        clear_tree(self.dup_tree)
        self.dup_by_iid, self.group_sizes = {}, {}
        groups = DuplicateDetector.find_duplicates(self.files)    # same logic the scanner uses
        # Files may have been quarantined/moved since the scan: only show copies that still exist.
        for group in groups:
            group["files"] = [f for f in group["files"] if os.path.isfile(f["absolute_path"])]
            group["copies"] = len(group["files"])
            group["reclaimable_bytes"] = (group["copies"] - 1) * group["size_bytes"]
        groups = [g for g in groups if g["copies"] > 1]
        for number, group in enumerate(groups, start=1):
            label = f"G{number}"
            self.group_sizes[label] = group["copies"]
            for f in sorted(group["files"], key=lambda item: item["absolute_path"]):
                iid = str(f["file_id"])
                self.dup_by_iid[iid] = dict(f, group=label)
                self.dup_tree.insert("", "end", iid=iid, values=(label, f["file_name"], f["absolute_path"],
                                     format_size(f["size_bytes"]), short_hash(f["sha256"])))
        if groups:
            self.summary_var.set(self.summary_var.get() + f"  |  {len(groups)} duplicate groups, "
                                 f"{format_size(total_reclaimable(groups))} potentially reclaimable")

    # ------------------------------------------------------------- quarantine
    def _quarantine_selected(self) -> None:
        selected = [self.dup_by_iid[iid] for iid in self.dup_tree.selection()]
        if not selected:
            messagebox.showinfo("FileSense", "Select one or more duplicate copies first.")
            return
        per_group = {}
        for f in selected:
            per_group[f["group"]] = per_group.get(f["group"], 0) + 1
        full = [g for g, n in per_group.items() if n >= self.group_sizes[g]]
        if full:
            messagebox.showwarning("FileSense", "You selected every copy in group(s) "
                                   f"{', '.join(full)}. Keep at least one copy of each group.")
            return
        if not messagebox.askyesno("Confirm quarantine",
                                   f"Move {len(selected)} file(s) to the quarantine folder?\n\n"
                                   "Nothing is deleted - you can restore them from the Quarantine page."):
            return
        results = self.run_safely(self.services.quarantine.quarantine_files, self._selected_scan_id(), selected)
        if results is None:
            return
        ok = sum(1 for r in results if r["status"] == "SUCCESS")
        failed = [r for r in results if r["status"] != "SUCCESS"]
        text = f"{ok} file(s) moved to quarantine."
        if failed:
            text += f"\n{len(failed)} failed:\n" + "\n".join(f"- {r['source']}: {r['message']}" for r in failed[:5])
        messagebox.showinfo("FileSense", text)
        self.app.set_status(f"Quarantined {ok} file(s)")
        self._load_selected()
