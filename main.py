"""FileSense entry point: logging -> config -> database check -> window."""
import sys
import tkinter as tk
from tkinter import messagebox

from config import SCHEMA_FILE, load_settings
from utils.logger import get_logger, setup_logging


def fail(title: str, message: str) -> None:
    """Show a readable error (dialog + console) instead of an unexplained traceback."""
    print(f"\n[{title}] {message}\n", file=sys.stderr)
    try:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(title, message)
        root.destroy()
    except tk.TclError:
        pass
    sys.exit(1)


def main() -> None:
    settings = load_settings()
    setup_logging(settings.log_dir)
    log = get_logger("main")
    log.info("FileSense starting")

    try:
        from database.connection import DatabaseError, DatabaseManager
        from database.repository import FileRepository, OperationRepository, ScanRepository
    except ImportError:
        fail("Missing package", "mysql-connector-python is not installed.\n\nRun:  pip install -r requirements.txt")
        return

    db = DatabaseManager(settings)
    try:
        db.get_connection(use_database=True).close()
    except DatabaseError as exc:
        if exc.errno == 1049:                                   # unknown database
            fail("Database not found", f"The database '{settings.db_name}' does not exist yet.\n\n"
                 f"Create it once with:\n  mysql -u {settings.db_user} -p < database\\schema.sql\n"
                 "(or run schema.sql in MySQL Workbench), then start FileSense again.")
        else:
            fail("MySQL unavailable", f"{exc}\n\nCheck that the MySQL service is running and that "
                 "FILESENSE_DB_USER / FILESENSE_DB_PASSWORD are set correctly (see README).")
        return

    try:
        if db.missing_tables():
            db.initialize_schema(SCHEMA_FILE)                   # database exists, tables missing
    except DatabaseError as exc:
        fail("Database setup failed", str(exc))
        return

    # Imported after the checks so a missing MySQL never breaks startup of the checks themselves.
    from analytics.analytics import AnalyticsService
    from organizer.file_categories import FileCategorizer
    from organizer.organizer import OrganizerService
    from organizer.quarantine import QuarantineService, reconcile_pending_operations
    from scanner.scan_manager import ScanManager
    from ui.app import AppServices, FileSenseApp

    scan_repo, file_repo, op_repo = ScanRepository(db), FileRepository(db), OperationRepository(db)
    interrupted = scan_repo.mark_interrupted_scans()
    reconciled = reconcile_pending_operations(op_repo)
    if interrupted or reconciled:
        log.warning("Recovered %s interrupted scan(s) and %s pending operation(s)", interrupted, reconciled)

    categorizer = FileCategorizer()
    services = AppServices(
        settings=settings, db=db, scan_repo=scan_repo, file_repo=file_repo, op_repo=op_repo,
        scan_manager=ScanManager(scan_repo, file_repo, db, settings.quarantine_dir, settings.chunk_size),
        analytics=AnalyticsService(scan_repo, op_repo),
        organizer=OrganizerService(op_repo, categorizer, settings.quarantine_dir),
        quarantine=QuarantineService(op_repo, settings.quarantine_dir),
        categorizer=categorizer)

    root = tk.Tk()
    app = FileSenseApp(root, services)

    def on_close() -> None:
        if services.scan_manager.is_running:
            if not messagebox.askyesno("FileSense", "A scan is still running. Stop it and exit?"):
                return
            services.scan_manager.cancel()
            services.scan_manager.wait(5)
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    log.info("GUI ready")
    root.mainloop()


if __name__ == "__main__":
    main()
