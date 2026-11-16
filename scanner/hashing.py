"""FileHasher: SHA-256 fingerprint of a file's content.

SHA-256 is NOT encryption. It is a one-way fingerprint: identical content always
gives the identical 64-character hex string; a different content (practically) never does.
"""
import hashlib
import os
import threading
from typing import Dict, Optional, Tuple

from config import HASH_CHUNK_SIZE
from utils.logger import get_logger

log = get_logger("hashing")

STATUS_OK = "OK"
STATUS_UNREADABLE = "UNREADABLE"
STATUS_CHANGED = "CHANGED"
STATUS_CANCELLED = "CANCELLED"   # internal only: never written to the database


class FileHasher:
    def __init__(self, chunk_size: int = HASH_CHUNK_SIZE) -> None:
        self.chunk_size = chunk_size

    @staticmethod
    def _snapshot(file_path: str) -> Tuple[int, int]:
        """(size, modification time in ns) - used to detect changes while hashing."""
        info = os.stat(file_path)
        return info.st_size, info.st_mtime_ns

    def calculate_hash(self, file_path: str, cancel_event: Optional[threading.Event] = None) -> Dict:
        """Return {'path', 'sha256', 'status', 'error'}.

        This runs inside worker threads: it only reads the file, it never touches
        Tkinter or MySQL.
        """
        result = {"path": file_path, "sha256": None, "status": STATUS_OK, "error": None}
        try:
            before = self._snapshot(file_path)
            digest = hashlib.sha256()
            bytes_read = 0
            with open(file_path, "rb") as handle:
                while True:
                    if cancel_event is not None and cancel_event.is_set():
                        result["status"] = STATUS_CANCELLED
                        return result
                    chunk = handle.read(self.chunk_size)      # never load the whole file
                    if not chunk:
                        break
                    digest.update(chunk)
                    bytes_read += len(chunk)
            after = self._snapshot(file_path)
        except OSError as exc:
            result["status"] = STATUS_UNREADABLE
            result["error"] = f"{file_path}: {exc.strerror or exc}"
            log.warning("Hashing failed: %s", result["error"])
            return result

        if before != after or bytes_read != before[0]:
            result["status"] = STATUS_CHANGED
            result["error"] = f"{file_path}: file changed while hashing"
            log.warning(result["error"])
            return result
        result["sha256"] = digest.hexdigest()
        return result
