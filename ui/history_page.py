"""Screen 7: History - past scans, plus the files and operations of the selected scan."""
from tkinter import ttk

from ui import BasePage, clear_tree, create_tree
from utils.formatting import format_size, format_status, format_timestamp


class HistoryPage(BasePage):
    title = "History"

    def __init__(self, parent, app) -> None:
        super().__init__(parent, app)
        self.scan_tree = create_tree(self, [("id", "Scan", 60), ("when", "Date", 150), ("path", "Root folder", 380),
                                            ("files", "Files", 80), ("dups", "Duplicates", 90),
                                            ("status", "Status", 100)], height=7, selectmode="browse")
        self.scan_tree.bind("<<TreeviewSelect>>", lambda e: self._show_details())
        ttk.Button(self, text="Use this scan in Results / Organizer", command=self._use_scan).pack(anchor="e", pady=6)
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)
        files_tab, ops_tab = ttk.Frame(notebook), ttk.Frame(notebook)
        notebook.add(files_tab, text="Files of selected scan")
        notebook.add(ops_tab, text="Operations of selected scan")
        self.file_tree = create_tree(files_tab, [("name", "File", 220), ("path", "Path", 420),
                                                 ("size", "Size", 90), ("status", "Status", 90)], height=8)
        self.op_tree = create_tree(ops_tab, [("id", "Op", 50), ("type", "Type", 90), ("src", "From", 300),
                                             ("dst", "To", 300), ("status", "Status", 90), ("err", "Error", 160)], height=8)

    def refresh(self) -> None:
        clear_tree(self.scan_tree)
        for s in self.run_safely(self.services.scan_repo.get_scan_history, 200) or []:
            self.scan_tree.insert("", "end", iid=str(s["scan_id"]),
                                  values=(s["scan_id"], format_timestamp(s["started_at"]), s["root_path"],
                                          s["total_files"], s["duplicate_files"], format_status(s["status"])))

    def _selected_id(self):
        selection = self.scan_tree.selection()
        return int(selection[0]) if selection else None

    def _show_details(self) -> None:
        scan_id = self._selected_id()
        if scan_id is None:
            return
        clear_tree(self.file_tree)
        for f in self.run_safely(self.services.file_repo.get_files, scan_id, 2000) or []:
            self.file_tree.insert("", "end", values=(f["file_name"], f["absolute_path"],
                                                     format_size(f["size_bytes"]), format_status(f["scan_status"])))
        clear_tree(self.op_tree)
        for o in self.run_safely(self.services.op_repo.get_operations, scan_id) or []:
            self.op_tree.insert("", "end", values=(o["operation_id"], format_status(o["operation_type"]),
                                                   o["source_path"], o["destination_path"],
                                                   format_status(o["status"]), o["error_message"] or ""))

    def _use_scan(self) -> None:
        scan_id = self._selected_id()
        if scan_id is not None:
            self.app.current_scan_id = scan_id
            self.app.set_status(f"Scan #{scan_id} selected")
