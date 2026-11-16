"""Screen 5: Organizer - preview first, confirm, then move files into category folders."""
import os
import tkinter as tk
from tkinter import messagebox, ttk

from ui import BasePage, clear_tree, create_tree


class OrganizerPage(BasePage):
    title = "Organizer"

    def __init__(self, parent, app) -> None:
        super().__init__(parent, app)
        self.plans = []
        self.scan = None
        self.scan_var = tk.StringVar()

        ttk.Label(self, textvariable=self.scan_var, style="Muted.TLabel").pack(anchor="w")
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=8)
        ttk.Label(bar, text="Category:").pack(side="left")
        self.category_combo = ttk.Combobox(bar, state="readonly", width=16,
                                           values=["All"] + self.services.categorizer.all_categories())
        self.category_combo.set("All")
        self.category_combo.pack(side="left", padx=6)
        ttk.Button(bar, text="Preview", style="Accent.TButton", command=self._preview).pack(side="left", padx=6)
        self.organize_button = ttk.Button(bar, text="Organize files...", command=self._organize, state="disabled")
        self.organize_button.pack(side="left")
        self.count_var = tk.StringVar()
        ttk.Label(bar, textvariable=self.count_var, style="Muted.TLabel").pack(side="left", padx=12)

        self.tree = create_tree(self, [("name", "File", 200), ("category", "Category", 90),
                                       ("src", "Current location", 330), ("dst", "Proposed location", 330)], height=12)
        ttk.Label(self, text="Operation results", style="Muted.TLabel").pack(anchor="w", pady=(8, 0))
        self.result_box = tk.Text(self, height=6, state="disabled", bg="white", relief="solid", bd=1,
                                  font=("Consolas", 9))
        self.result_box.pack(fill="x")

    def refresh(self) -> None:
        scan_id = self.app.current_scan_id
        self.scan = self.run_safely(self.services.scan_repo.get_scan, scan_id) if scan_id else None
        if self.scan:
            self.scan_var.set(f"Scan #{scan_id}: files will be sorted into category folders inside "
                              f"{self.scan['root_path']}")
        else:
            self.scan_var.set("Run a scan first (or choose one in History), then come back here.")
        self.plans = []
        clear_tree(self.tree)
        self.count_var.set("")
        self.organize_button.config(state="disabled")

    def _preview(self) -> None:
        if not self.scan:
            messagebox.showinfo("FileSense", "There is no scan to organize yet.")
            return
        files = self.run_safely(self.services.file_repo.get_files, self.scan["scan_id"]) or []
        self.plans = self.services.organizer.build_preview(files, self.scan["root_path"],
                                                           self.category_combo.get())
        clear_tree(self.tree)
        for plan in self.plans:
            self.tree.insert("", "end", values=(plan["file_name"], plan["category"],
                                                plan["source"], plan["destination"]))
        self.count_var.set(f"{len(self.plans)} file(s) would be moved")
        self.organize_button.config(state="normal" if self.plans else "disabled")

    def _organize(self) -> None:
        if not self.plans:
            return
        if not messagebox.askyesno("Confirm organization",
                                   f"Move {len(self.plans)} file(s) into category folders?\n\n"
                                   "Existing files are never overwritten."):
            return
        results = self.run_safely(self.services.organizer.execute, self.scan["scan_id"], self.plans)
        if results is None:
            return
        ok = sum(1 for r in results if r["status"] == "SUCCESS")
        self.result_box.config(state="normal")
        self.result_box.delete("1.0", "end")
        self.result_box.insert("end", f"{ok} moved, {len(results) - ok} failed\n")
        for r in results:
            if r["status"] != "SUCCESS":
                self.result_box.insert("end", f"FAILED {os.path.basename(r['source'])}: {r['message']}\n")
        self.result_box.config(state="disabled")
        self.app.set_status(f"Organized {ok} file(s)")
        self.plans = []
        clear_tree(self.tree)
        self.organize_button.config(state="disabled")
