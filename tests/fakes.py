"""In-memory stand-ins for the MySQL repositories so unit tests need no database."""
import threading
from contextlib import contextmanager


class FakeOperationRepository:
    def __init__(self):
        self.rows = {}
        self._next = 1
        self._lock = threading.Lock()

    def create_operation(self, scan_id, file_id, operation_type, source_path, destination_path):
        with self._lock:
            op_id = self._next
            self._next += 1
            self.rows[op_id] = {"operation_id": op_id, "scan_id": scan_id, "file_id": file_id,
                                "operation_type": operation_type, "source_path": source_path,
                                "destination_path": destination_path, "status": "PENDING",
                                "error_message": None}
            return op_id

    def update_status(self, operation_id, status, error_message=None):
        self.rows[operation_id]["status"] = status
        self.rows[operation_id]["error_message"] = error_message

    def by_type(self, operation_type):
        return [r for r in self.rows.values() if r["operation_type"] == operation_type]


class FakeScanRepository:
    def __init__(self):
        self.scans = {}

    def create_scan(self, root_path):
        scan_id = len(self.scans) + 1
        self.scans[scan_id] = {"root_path": root_path, "status": "RUNNING", "stats": {}}
        return scan_id

    def update_scan(self, scan_id, status, stats=None, cursor=None):
        self.scans[scan_id].update(status=status, stats=stats or {})


class FakeFileRepository:
    def __init__(self):
        self.saved = {}

    def insert_files(self, scan_id, files, cursor=None, batch=1000):
        self.saved[scan_id] = list(files)
        return len(self.saved[scan_id])


class FakeDatabase:
    """Only provides transaction(); a real one would hand out a MySQL cursor."""

    @contextmanager
    def transaction(self):
        yield None
