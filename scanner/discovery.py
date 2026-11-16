"""DirectoryScanner: finds files and collects metadata. It NEVER modifies anything."""
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional

from config import MAX_PATH_LENGTH
from utils.logger import get_logger

log = get_logger("scanner")


@dataclass
class DiscoveryResult:
    """Return value of scan_directory().

    files:       list of dicts with keys absolute_path, file_name, extension,
                 size_bytes, modified_at (datetime or None)
    errors:      list of human-readable error messages (inaccessible folders/files)
    error_count: len(errors)
    """
    files: List[Dict] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return len(self.errors)


class DirectoryScanner:
    def __init__(self, excluded_dirs: Optional[List] = None, recursive: bool = True,
                 cancel_event: Optional[threading.Event] = None,
                 progress_callback: Optional[Callable[[int, int, str], None]] = None) -> None:
        # Normalised absolute paths of folders that must never be scanned (e.g. quarantine).
        self.excluded = [self._norm(p) for p in (excluded_dirs or [])]
        self.recursive = recursive
        self.cancel_event = cancel_event
        self.progress_callback = progress_callback   # called as (files_found, errors, current_path)

    @staticmethod
    def _norm(path) -> str:
        return os.path.normcase(os.path.abspath(str(path)))

    def _is_excluded(self, path: str) -> bool:
        norm = self._norm(path)
        return any(norm == ex or norm.startswith(ex + os.sep) for ex in self.excluded)

    def scan_directory(self, root_path: str) -> DiscoveryResult:
        """Walk root_path (iteratively, so deep trees cannot overflow the call stack)."""
        result = DiscoveryResult()
        seen_files = set()          # avoids processing the same path twice
        seen_dirs = set()
        pending = [os.path.abspath(root_path)]

        if not os.path.isdir(root_path):
            result.errors.append(f"Not a directory: {root_path}")
            return result

        while pending:
            if self.cancel_event is not None and self.cancel_event.is_set():
                break
            current = pending.pop()
            real = os.path.normcase(os.path.realpath(current))
            if real in seen_dirs or self._is_excluded(current):
                continue
            seen_dirs.add(real)
            try:
                with os.scandir(current) as entries:
                    for entry in entries:
                        self._handle_entry(entry, pending, seen_files, result)
            except OSError as exc:
                msg = f"Cannot open folder {current}: {exc.strerror or exc}"
                result.errors.append(msg)
                log.warning(msg)
            if self.progress_callback:
                self.progress_callback(len(result.files), result.error_count, current)
        return result

    def _handle_entry(self, entry: os.DirEntry, pending: list, seen_files: set,
                      result: DiscoveryResult) -> None:
        try:
            if entry.is_symlink():                       # never follow symbolic links
                return
            if entry.is_dir(follow_symlinks=False):
                if self.recursive:
                    pending.append(entry.path)
                return
            if not entry.is_file(follow_symlinks=False):
                return
            path = os.path.abspath(entry.path)
            key = os.path.normcase(path)
            if key in seen_files or self._is_excluded(path):
                return
            if len(path) > MAX_PATH_LENGTH:
                result.errors.append(f"Path too long, skipped: {path[:80]}...")
                return
            info = entry.stat(follow_symlinks=False)
            seen_files.add(key)
            result.files.append({
                "absolute_path": path,
                "file_name": entry.name,
                "extension": os.path.splitext(entry.name)[1].lower()[:20],
                "size_bytes": info.st_size,
                "modified_at": datetime.fromtimestamp(info.st_mtime),
            })
        except OSError as exc:                           # file vanished / permission denied
            msg = f"Cannot read {entry.path}: {exc.strerror or exc}"
            result.errors.append(msg)
            log.warning(msg)
