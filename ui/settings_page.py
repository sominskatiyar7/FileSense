"""Screen 8: Settings - connection status, worker count, folders, app info. No password is shown."""
import tkinter as tk
from tkinter import messagebox, ttk

from config import APP_NAME, APP_TITLE, APP_VERSION, MAX_HASH_WORKERS, MIN_HASH_WORKERS
from ui import BasePage


class SettingsPage(BasePage):
    title = "Settings"

    def __init__(self, parent, app) -> None:
        super().__init__(parent, app)
        s = self.services.settings
        self.db_var = tk.StringVar()
        self.workers_var = tk.StringVar(value=str(s.hash_workers))
        box = ttk.LabelFrame(self, text=" Application settings ", padding=14)
        box.pack(fill="x")
        rows = [("Database", self.db_var), ("Database name", tk.StringVar(value=f"{s.db_name} @ {s.db_host}:{s.db_port}")),
                ("Quarantine folder", tk.StringVar(value=str(s.quarantine_dir))),
                ("Log folder", tk.StringVar(value=str(s.log_dir))),
                ("Application", tk.StringVar(value=f"{APP_NAME} v{APP_VERSION} - {APP_TITLE}"))]
        for r, (label, var) in enumerate(rows):
            ttk.Label(box, text=label + ":", style="Muted.TLabel").grid(row=r, column=0, sticky="w", pady=3)
            ttk.Label(box, textvariable=var).grid(row=r, column=1, sticky="w", padx=12)
        r = len(rows)
        ttk.Label(box, text="Hashing workers:", style="Muted.TLabel").grid(row=r, column=0, sticky="w", pady=8)
        spin = ttk.Spinbox(box, from_=MIN_HASH_WORKERS, to=MAX_HASH_WORKERS, textvariable=self.workers_var, width=5)
        spin.grid(row=r, column=1, sticky="w", padx=12)
        ttk.Button(box, text="Apply", command=self._apply_workers).grid(row=r, column=2)
        ttk.Button(self, text="Re-check database connection", command=self.refresh).pack(anchor="w", pady=12)

    def refresh(self) -> None:
        ok, message = self.services.db.check_connection()
        self.db_var.set("Connected" if ok else f"NOT connected - {message}")

    def _apply_workers(self) -> None:
        try:
            value = int(self.workers_var.get())
        except ValueError:
            value = 0
        if not MIN_HASH_WORKERS <= value <= MAX_HASH_WORKERS:
            messagebox.showwarning("FileSense", f"Workers must be a whole number from "
                                   f"{MIN_HASH_WORKERS} to {MAX_HASH_WORKERS}.")
            self.workers_var.set(str(self.services.settings.hash_workers))
            return
        self.services.settings.hash_workers = value
        self.app.set_status(f"Hashing workers set to {value}")
