"""Screen 6: Quarantine - list quarantined files and restore them."""
import os
from tkinter import filedialog, messagebox, ttk

from ui import BasePage, clear_tree, create_tree
from utils.formatting import format_status, format_timestamp


class QuarantinePage(BasePage):
    title = "Quarantine"

    def __init__(self, parent, app) -> None:
        super().__init__(parent, app)
        self.rows = {}
        ttk.Label(self, text="Files here are safe, not deleted. Select a file and restore it to its original place.",
                  style="Muted.TLabel").pack(anchor="w", pady=(0, 6))
        self.tree = create_tree(self, [("name", "File name", 200), ("orig", "Original path", 340),
                                       ("quar", "Quarantine path", 340), ("when", "Date", 140),
                                       ("status", "Status", 90)], selectmode="browse")
        ttk.Button(self, text="Restore selected file", style="Accent.TButton",
                   command=self._restore).pack(anchor="e", pady=8)

    def refresh(self) -> None:
        clear_tree(self.tree)
        rows = self.run_safely(self.services.op_repo.get_quarantined_files) or []
        self.rows = {str(r["operation_id"]): r for r in rows}
        for r in rows:
            self.tree.insert("", "end", iid=str(r["operation_id"]),
                             values=(os.path.basename(r["source_path"]), r["source_path"], r["destination_path"],
                                     format_timestamp(r["operation_at"]), "Quarantined"))

    def _restore(self) -> None:
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("FileSense", "Select a quarantined file first.")
            return
        op = self.rows[selection[0]]
        result = self.run_safely(self.services.quarantine.restore, op)
        if result is None:
            return
        if result["status"] == "CONFLICT":
            if not messagebox.askyesno("File already exists",
                                       f"A file already exists at:\n{result['destination']}\n\n"
                                       "It will NOT be overwritten. Choose a different location?"):
                return
            new_path = filedialog.asksaveasfilename(title="Restore to...", initialfile=os.path.basename(op["source_path"]),
                                                    initialdir=os.path.dirname(op["source_path"]))
            if not new_path:
                return
            result = self.run_safely(self.services.quarantine.restore, op, os.path.normpath(new_path))
            if result is None:
                return
        if result["status"] == "SUCCESS":
            messagebox.showinfo("FileSense", f"Restored to:\n{result['destination']}")
            self.app.set_status("File restored")
        else:
            messagebox.showerror("FileSense", f"{format_status(result['status'])}: {result['message']}")
        self.refresh()
