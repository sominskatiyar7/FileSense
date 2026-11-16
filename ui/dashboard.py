"""Screen 1: Dashboard - every number comes from MySQL through AnalyticsService."""
import tkinter as tk
from tkinter import ttk

from ui import BasePage, StatCard, clear_tree, create_tree
from utils.formatting import format_size, format_status, format_timestamp


class DashboardPage(BasePage):
    title = "Dashboard"

    def __init__(self, parent, app) -> None:
        super().__init__(parent, app)
        self.cards = {}
        grid = ttk.Frame(self)
        grid.pack(fill="x")
        captions = [("total_files", "Files scanned"), ("total_bytes", "Storage scanned"),
                    ("duplicate_groups", "Duplicate groups"), ("duplicate_files", "Duplicate files"),
                    ("reclaimable_bytes", "Potentially reclaimable"), ("scans_run", "Scans run"),
                    ("organized_files", "Files organized"), ("quarantined_files", "Files quarantined"),
                    ("restored_files", "Files restored")]
        for index, (key, caption) in enumerate(captions):
            card = StatCard(grid, caption)
            card.grid(row=index // 5, column=index % 5, padx=6, pady=6, sticky="nsew")
            grid.columnconfigure(index % 5, weight=1)
            self.cards[key] = card
        ttk.Label(self, text="Totals use the newest completed scan of each scanned folder.",
                  style="Muted.TLabel").pack(anchor="w", pady=(2, 8))

        ttk.Label(self, text="Recent scans", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self.scan_tree = create_tree(self, [("id", "Scan", 60), ("when", "Started", 150),
                                            ("path", "Folder", 420), ("files", "Files", 80),
                                            ("dups", "Dup. groups", 90), ("status", "Status", 100)], height=5)
        ttk.Label(self, text="Recent file operations", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(10, 0))
        self.op_tree = create_tree(self, [("id", "Op", 60), ("type", "Type", 100), ("src", "From", 330),
                                          ("dst", "To", 330), ("status", "Status", 90)], height=5)

    def refresh(self) -> None:
        stats = self.run_safely(self.services.analytics.get_dashboard_stats)
        if stats is None:
            self.app.set_status("Could not load dashboard data (is MySQL running?)")
            return
        for key, card in self.cards.items():
            value = stats[key]
            card.set(format_size(value) if key.endswith("_bytes") else f"{value:,}")
        clear_tree(self.scan_tree)
        for s in stats["recent_scans"]:
            self.scan_tree.insert("", "end", values=(s["scan_id"], format_timestamp(s["started_at"]),
                                 s["root_path"], s["total_files"], s["duplicate_groups"],
                                 format_status(s["status"])))
        clear_tree(self.op_tree)
        for o in stats["recent_operations"]:
            self.op_tree.insert("", "end", values=(o["operation_id"], format_status(o["operation_type"]),
                                o["source_path"], o["destination_path"], format_status(o["status"])))
