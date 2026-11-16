"""Screens 2 and 3: Scan Configuration (top) and Live Scanner (bottom).

The scan runs in a coordinator thread. This page only (a) starts/cancels it and
(b) displays events that FileSenseApp pulled off the queue on the Tk main thread.
"""
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ui import COLORS, BasePage
from utils.formatting import format_size
from utils.progress import EventType


class ScanPage(BasePage):
    title = "Scan"

    def __init__(self, parent, app) -> None:
        super().__init__(parent, app)
        self.folder_var = tk.StringVar()
        self.recursive_var = tk.BooleanVar(value=True)
        self.state_var = tk.StringVar(value="Idle")
        self.operation_var = tk.StringVar(value="-")
        self.discovered_var = tk.StringVar(value="0")
        self.hashed_var = tk.StringVar(value="0 / 0")
        self.errors_var = tk.StringVar(value="0")
        self.cancel_var = tk.StringVar(value="Not requested")

        config = ttk.LabelFrame(self, text=" Scan configuration ", padding=12)
        config.pack(fill="x")
        row = ttk.Frame(config)
        row.pack(fill="x")
        ttk.Entry(row, textvariable=self.folder_var, state="readonly").pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Browse...", command=self._choose_folder).pack(side="left", padx=(8, 0))
        ttk.Checkbutton(config, text="Scan sub-folders (recursive)", variable=self.recursive_var).pack(anchor="w", pady=6)
        self.workers_label = ttk.Label(config, text="")
        self.workers_label.pack(anchor="w")
        buttons = ttk.Frame(config)
        buttons.pack(anchor="w", pady=(10, 0))
        self.start_button = ttk.Button(buttons, text="Start Scan", style="Accent.TButton", command=self._start)
        self.start_button.pack(side="left")
        self.cancel_button = ttk.Button(buttons, text="Cancel Scan", style="Danger.TButton",
                                        command=self._cancel, state="disabled")
        self.cancel_button.pack(side="left", padx=8)

        live = ttk.LabelFrame(self, text=" Live scanner ", padding=12)
        live.pack(fill="x", pady=14)
        grid = ttk.Frame(live)
        grid.pack(fill="x")
        for r, (label, var) in enumerate([("Status", self.state_var), ("Files discovered", self.discovered_var),
                                          ("Files hashed", self.hashed_var), ("Errors", self.errors_var),
                                          ("Cancellation", self.cancel_var), ("Current operation", self.operation_var)]):
            ttk.Label(grid, text=label + ":", style="Muted.TLabel").grid(row=r, column=0, sticky="w", pady=2)
            ttk.Label(grid, textvariable=var, wraplength=700).grid(row=r, column=1, sticky="w", padx=12)
        self.progress = ttk.Progressbar(live, mode="determinate", maximum=100)
        self.progress.pack(fill="x", pady=(10, 0))

        ttk.Label(self, text="Problems found during the scan", style="Muted.TLabel").pack(anchor="w")
        self.error_box = tk.Text(self, height=6, state="disabled", bg="white", relief="solid", bd=1,
                                 font=("Consolas", 9))
        self.error_box.pack(fill="both", expand=True)

    def refresh(self) -> None:
        self.workers_label.config(text=f"Hashing workers: {self.services.settings.hash_workers} "
                                       f"(change in Settings)")

    # ------------------------------------------------------------- user actions
    def _choose_folder(self) -> None:
        folder = filedialog.askdirectory(title="Choose a folder to scan")
        if folder:
            self.folder_var.set(os.path.normpath(folder))

    def _start(self) -> None:
        folder = self.folder_var.get()
        if not folder or not os.path.isdir(folder):
            messagebox.showwarning("FileSense", "Please choose an existing folder first.")
            return
        if not os.access(folder, os.R_OK):
            messagebox.showwarning("FileSense", "You do not have permission to read this folder.")
            return
        manager = self.services.scan_manager
        if manager.is_running:
            return
        self._reset_display()
        try:
            manager.start_scan(folder, self.recursive_var.get(), self.services.settings.hash_workers)
        except Exception as exc:
            messagebox.showerror("FileSense", f"Could not start the scan:\n{exc}")
            return
        self.state_var.set("Starting...")
        self.start_button.config(state="disabled")
        self.cancel_button.config(state="normal")

    def _cancel(self) -> None:
        self.services.scan_manager.cancel()
        self.cancel_var.set("Requested - waiting for running tasks to stop")
        self.cancel_button.config(state="disabled")

    def _reset_display(self) -> None:
        for var, value in [(self.discovered_var, "0"), (self.hashed_var, "0 / 0"), (self.errors_var, "0"),
                           (self.cancel_var, "Not requested"), (self.operation_var, "-")]:
            var.set(value)
        self.progress["value"] = 0
        self.error_box.config(state="normal")
        self.error_box.delete("1.0", "end")
        self.error_box.config(state="disabled")

    # ------------------------------------------------- events (main thread only)
    def handle_event(self, event) -> None:
        data = event.data
        if event.type == EventType.SCAN_STARTED:
            self.state_var.set(f"Scanning (scan #{data['scan_id']})")
            self.operation_var.set("Discovering files...")
        elif event.type == EventType.DISCOVERY_PROGRESS:
            self.discovered_var.set(f"{data['discovered']:,}")
            self.errors_var.set(str(data["errors"]))
            self.operation_var.set(f"Discovering: {data['current']}")
        elif event.type == EventType.HASH_PROGRESS:
            self.hashed_var.set(f"{data['hashed']:,} / {data['total']:,}")
            self.errors_var.set(str(data["errors"]))
            self.progress["value"] = data["percent"]
            self.operation_var.set(f"Hashing: {data['current']}")
        elif event.type == EventType.ERROR:
            self._log_problem(data["message"])
        elif event.type in (EventType.SCAN_COMPLETED, EventType.SCAN_CANCELLED):
            summary = data["summary"]
            done = event.type == EventType.SCAN_COMPLETED
            self.state_var.set("Completed" if done else "Cancelled (partial results saved)")
            self.operation_var.set(
                f"{summary['total_files']:,} files, {format_size(summary['total_bytes'])}; "
                f"{summary['duplicate_groups']} duplicate groups; "
                f"{format_size(summary['reclaimable_bytes'])} reclaimable")
            if done:
                self.progress["value"] = 100
            self.errors_var.set(str(summary["error_count"]))
            self._finish()
        elif event.type == EventType.SCAN_FAILED:
            self.state_var.set("Failed")
            self.operation_var.set(data["message"])
            messagebox.showerror("FileSense", f"The scan failed:\n{data['message']}")
            self._finish()

    def _finish(self) -> None:
        self.start_button.config(state="normal")
        self.cancel_button.config(state="disabled")

    def _log_problem(self, message: str) -> None:
        self.error_box.config(state="normal")
        self.error_box.insert("end", message + "\n")
        self.error_box.config(state="disabled")
