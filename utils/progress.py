"""Event and progress helpers shared by the scan manager (producer) and the GUI (consumer).

EVENT TYPES (put on a queue.Queue by the coordinator thread, read by the Tk main thread)
-----------------------------------------------------------------------------------------
SCAN_STARTED        data: scan_id (int), root_path (str)
DISCOVERY_PROGRESS  data: discovered (int), errors (int), current (str)
HASH_PROGRESS       data: hashed (int), total (int), percent (float), errors (int), current (str)
SCAN_COMPLETED      data: summary (dict with scan_id, status, total_files, total_bytes,
                          duplicate_groups, duplicate_files, reclaimable_bytes, error_count)
SCAN_CANCELLED      data: summary (same shape as above, status == 'CANCELLED')
SCAN_FAILED         data: scan_id (int or None), message (str)
ERROR               data: message (str)  - a non-fatal problem (e.g. one unreadable file)
"""
import threading
from dataclasses import dataclass, field


class EventType:
    SCAN_STARTED = "SCAN_STARTED"
    DISCOVERY_PROGRESS = "DISCOVERY_PROGRESS"
    HASH_PROGRESS = "HASH_PROGRESS"
    SCAN_COMPLETED = "SCAN_COMPLETED"
    SCAN_CANCELLED = "SCAN_CANCELLED"
    SCAN_FAILED = "SCAN_FAILED"
    ERROR = "ERROR"


@dataclass
class ScanEvent:
    """One message travelling from the coordinator thread to the GUI."""
    type: str
    data: dict = field(default_factory=dict)


def make_event(event_type: str, **data) -> ScanEvent:
    return ScanEvent(type=event_type, data=data)


class ProgressTracker:
    """Thread-safe counters for a running scan."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.discovered = 0
        self.hash_total = 0
        self.hashed = 0
        self.errors = 0

    def set_discovered(self, count: int, errors: int) -> None:
        with self._lock:
            self.discovered = count
            self.errors = errors

    def set_hash_total(self, total: int) -> None:
        with self._lock:
            self.hash_total = total
            self.hashed = 0

    def add_hashed(self, failed: bool = False) -> None:
        with self._lock:
            self.hashed += 1
            if failed:
                self.errors += 1

    def percent(self) -> float:
        with self._lock:
            if self.hash_total == 0:
                return 100.0
            return round(self.hashed * 100.0 / self.hash_total, 1)

    def snapshot(self) -> dict:
        with self._lock:
            return {"discovered": self.discovered, "hashed": self.hashed,
                    "total": self.hash_total, "errors": self.errors}
