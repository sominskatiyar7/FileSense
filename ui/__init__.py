"""Shared GUI helpers: colours, base page class, table (Treeview) builder, stat cards."""
import tkinter as tk
from tkinter import ttk
from typing import List, Tuple

COLORS = {
    "sidebar": "#1e2a3a", "sidebar_hover": "#2c3e55", "sidebar_active": "#3d7eff",
    "bg": "#f4f6fa", "card": "#ffffff", "text": "#1f2933", "muted": "#6b7785",
    "accent": "#3d7eff", "danger": "#d64545", "success": "#2e9d6a", "border": "#dde3ec",
}
FONT = "Segoe UI"


class BasePage(ttk.Frame):
    """Every screen derives from this. `app` is the FileSenseApp (gives access to services)."""
    title = ""

    def __init__(self, parent, app) -> None:
        super().__init__(parent, style="Page.TFrame", padding=(24, 18))
        self.app = app
        self.services = app.services
        ttk.Label(self, text=self.title, style="Title.TLabel").pack(anchor="w", pady=(0, 12))

    def refresh(self) -> None:
        """Called every time the page is shown. Reload data from MySQL here."""

    def run_safely(self, action, *args, **kwargs):
        """Call a backend method; show a friendly dialog if the database/file system fails."""
        from tkinter import messagebox
        try:
            return action(*args, **kwargs)
        except Exception as exc:
            messagebox.showerror("FileSense", f"Something went wrong:\n{exc}")
            return None


def create_tree(parent, columns: List[Tuple[str, str, int]], height: int = 10,
                selectmode: str = "extended") -> ttk.Treeview:
    """columns = [(id, heading, width), ...]. Returns a Treeview with scrollbars, packed in parent."""
    holder = ttk.Frame(parent)
    holder.pack(fill="both", expand=True)
    tree = ttk.Treeview(holder, columns=[c[0] for c in columns], show="headings",
                        height=height, selectmode=selectmode)
    for col_id, heading, width in columns:
        tree.heading(col_id, text=heading)
        tree.column(col_id, width=width, anchor="w")
    vbar = ttk.Scrollbar(holder, orient="vertical", command=tree.yview)
    hbar = ttk.Scrollbar(holder, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=vbar.set, xscrollcommand=hbar.set)
    tree.grid(row=0, column=0, sticky="nsew")
    vbar.grid(row=0, column=1, sticky="ns")
    hbar.grid(row=1, column=0, sticky="ew")
    holder.rowconfigure(0, weight=1)
    holder.columnconfigure(0, weight=1)
    return tree


def clear_tree(tree: ttk.Treeview) -> None:
    tree.delete(*tree.get_children())


class StatCard(tk.Frame):
    """A small white box showing one big number and a caption."""

    def __init__(self, parent, caption: str) -> None:
        super().__init__(parent, bg=COLORS["card"], highlightbackground=COLORS["border"],
                         highlightthickness=1, padx=16, pady=12)
        self.value = tk.Label(self, text="-", font=(FONT, 20, "bold"), bg=COLORS["card"],
                              fg=COLORS["accent"])
        self.value.pack(anchor="w")
        tk.Label(self, text=caption, font=(FONT, 10), bg=COLORS["card"],
                 fg=COLORS["muted"]).pack(anchor="w")

    def set(self, text: str) -> None:
        self.value.config(text=text)
