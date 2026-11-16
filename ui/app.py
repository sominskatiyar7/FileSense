"""FileSenseApp: main window = sidebar + page area + status bar.

It also owns the ONLY place that reads the scan event queue (root.after polling),
then forwards each event to the pages. Background threads never touch widgets.
"""
import queue
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk
from typing import Any, Dict, Optional

from config import APP_NAME, APP_TITLE, Settings
from ui import COLORS, FONT
from ui.dashboard import DashboardPage
from ui.history_page import HistoryPage
from ui.organizer_page import OrganizerPage
from ui.quarantine_page import QuarantinePage
from ui.results_page import ResultsPage
from ui.scan_page import ScanPage
from ui.settings_page import SettingsPage
from utils.progress import EventType


@dataclass
class AppServices:
    """Everything the GUI is allowed to call (business + data layers)."""
    settings: Settings
    db: Any
    scan_repo: Any
    file_repo: Any
    op_repo: Any
    scan_manager: Any
    analytics: Any
    organizer: Any
    quarantine: Any
    categorizer: Any


class FileSenseApp:
    POLL_MS = 100
    MAX_EVENTS_PER_POLL = 300

    PAGES = [("dashboard", "Dashboard", DashboardPage), ("scan", "Scan", ScanPage),
             ("results", "Results", ResultsPage), ("organizer", "Organizer", OrganizerPage),
             ("quarantine", "Quarantine", QuarantinePage), ("history", "History", HistoryPage),
             ("settings", "Settings", SettingsPage)]

    def __init__(self, root: tk.Tk, services: AppServices) -> None:
        self.root = root
        self.services = services
        self.current_scan_id: Optional[int] = None
        self.pages: Dict[str, ttk.Frame] = {}
        self.nav_buttons: Dict[str, tk.Button] = {}
        self.status_var = tk.StringVar(value="Ready")

        root.title(f"{APP_NAME} - {APP_TITLE}")
        root.geometry("1180x720")
        root.minsize(1000, 620)
        self._configure_style()
        self._build_layout()
        self.show_page("dashboard")
        root.after(self.POLL_MS, self._poll_events)

    # ------------------------------------------------------------------ layout
    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        self.root.configure(bg=COLORS["bg"])
        style.configure("Page.TFrame", background=COLORS["bg"])
        style.configure("TFrame", background=COLORS["bg"])
        style.configure("TLabel", background=COLORS["bg"], foreground=COLORS["text"], font=(FONT, 10))
        style.configure("Title.TLabel", font=(FONT, 18, "bold"), foreground=COLORS["text"])
        style.configure("Muted.TLabel", foreground=COLORS["muted"])
        style.configure("TButton", font=(FONT, 10), padding=(12, 6))
        style.configure("Accent.TButton", background=COLORS["accent"], foreground="white")
        style.map("Accent.TButton", background=[("active", "#2f66d6"), ("disabled", "#a9bde6")])
        style.configure("Danger.TButton", background=COLORS["danger"], foreground="white")
        style.map("Danger.TButton", background=[("active", "#b53636"), ("disabled", "#e3a8a8")])
        style.configure("Treeview", rowheight=24, font=(FONT, 10), background="white",
                        fieldbackground="white")
        style.configure("Treeview.Heading", font=(FONT, 10, "bold"))
        style.configure("TNotebook", background=COLORS["bg"])
        style.configure("TCheckbutton", background=COLORS["bg"])
        style.configure("Horizontal.TProgressbar", troughcolor=COLORS["border"],
                        background=COLORS["accent"])

    def _build_layout(self) -> None:
        sidebar = tk.Frame(self.root, bg=COLORS["sidebar"], width=200)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        tk.Label(sidebar, text="FileSense", font=(FONT, 20, "bold"), bg=COLORS["sidebar"],
                 fg="white").pack(anchor="w", padx=20, pady=(24, 0))
        tk.Label(sidebar, text="Organize. Deduplicate.", font=(FONT, 9), bg=COLORS["sidebar"],
                 fg="#9fb0c7").pack(anchor="w", padx=20, pady=(0, 24))

        for key, label, _ in self.PAGES:
            button = tk.Button(sidebar, text=label, anchor="w", font=(FONT, 11), relief="flat",
                               bg=COLORS["sidebar"], fg="white", activebackground=COLORS["sidebar_hover"],
                               activeforeground="white", padx=20, pady=10, bd=0, cursor="hand2",
                               command=lambda k=key: self.show_page(k))
            button.pack(fill="x")
            self.nav_buttons[key] = button

        right = tk.Frame(self.root, bg=COLORS["bg"])
        right.pack(side="left", fill="both", expand=True)
        status = tk.Label(right, textvariable=self.status_var, anchor="w", bg=COLORS["border"],
                          fg=COLORS["text"], font=(FONT, 9), padx=12, pady=4)
        status.pack(side="bottom", fill="x")
        container = tk.Frame(right, bg=COLORS["bg"])
        container.pack(fill="both", expand=True)
        for key, _, page_class in self.PAGES:
            page = page_class(container, self)
            page.place(relx=0, rely=0, relwidth=1, relheight=1)
            self.pages[key] = page

    # -------------------------------------------------------------- navigation
    def show_page(self, key: str) -> None:
        for name, button in self.nav_buttons.items():
            button.config(bg=COLORS["sidebar_active"] if name == key else COLORS["sidebar"])
        page = self.pages[key]
        page.refresh()
        page.tkraise()

    def set_status(self, text: str) -> None:
        self.status_var.set(text)

    # ------------------------------------------------------ event queue polling
    def _poll_events(self) -> None:
        """Runs on the Tk main thread every POLL_MS. This is how worker results reach the GUI."""
        event_queue = self.services.scan_manager.event_queue
        for _ in range(self.MAX_EVENTS_PER_POLL):
            try:
                event = event_queue.get_nowait()
            except queue.Empty:
                break
            self._handle_event(event)
        self.root.after(self.POLL_MS, self._poll_events)

    def _handle_event(self, event) -> None:
        if event.type == EventType.SCAN_STARTED:
            self.current_scan_id = event.data["scan_id"]
            self.set_status(f"Scan #{self.current_scan_id} running...")
        elif event.type in (EventType.SCAN_COMPLETED, EventType.SCAN_CANCELLED):
            summary = event.data["summary"]
            self.current_scan_id = summary["scan_id"]
            self.set_status(f"Scan #{summary['scan_id']} {summary['status'].lower()}: "
                            f"{summary['total_files']} files, {summary['duplicate_groups']} duplicate groups")
        elif event.type == EventType.SCAN_FAILED:
            self.set_status(f"Scan failed: {event.data['message']}")
        self.pages["scan"].handle_event(event)
