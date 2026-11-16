"""ScanManager: coordinates a whole scan.

THREADS
  * Tkinter main thread : starts the scan, polls `event_queue` with root.after(), draws widgets.
  * Coordinator thread  : discovery, schedules hashing, collects results, writes to MySQL,
                          finds duplicates, publishes events. (one thread per scan)
  * Hash worker threads : ThreadPoolExecutor workers. They ONLY open files and compute
                          SHA-256. No Tkinter, no MySQL.
"""
import os
import queue
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

from analytics.analytics import total_size
from scanner.discovery import DirectoryScanner
from scanner.duplicate_finder import DuplicateDetector
from scanner.hashing import STATUS_CANCELLED, FileHasher
from utils.logger import get_logger
from utils.progress import EventType, ProgressTracker, make_event

log = get_logger("scan")


class ScanManager:
    def __init__(self, scan_repo, file_repo, db_manager, quarantine_dir,
                 chunk_size: int = 1024 * 1024) -> None:
        self.scan_repo = scan_repo
        self.file_repo = file_repo
        self.db = db_manager                      # used only by the coordinator for transactions
        self.quarantine_dir = quarantine_dir
        self.hasher = FileHasher(chunk_size)
        self.detector = DuplicateDetector()
        self.event_queue: "queue.Queue" = queue.Queue()
        self.cancel_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.tracker = ProgressTracker()

    # ------------------------------------------------------------ public API (main thread)
    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start_scan(self, root_path: str, recursive: bool = True, workers: int = 4) -> None:
        if self.is_running:
            raise RuntimeError("A scan is already running")
        self.cancel_event.clear()
        self.tracker = ProgressTracker()
        self._thread = threading.Thread(target=self._run, args=(root_path, recursive, workers),
                                        name="ScanCoordinator", daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        """Ask the running scan to stop. Safe to call from any thread."""
        self.cancel_event.set()

    def wait(self, timeout: Optional[float] = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)

    # ------------------------------------------------------------ coordinator thread
    def _emit(self, event_type: str, **data) -> None:
        self.event_queue.put(make_event(event_type, **data))

    def _run(self, root_path: str, recursive: bool, workers: int) -> None:
        scan_id = None
        try:
            scan_id = self.scan_repo.create_scan(root_path)
            log.info("Scan %s started: %s", scan_id, root_path)
            self._emit(EventType.SCAN_STARTED, scan_id=scan_id, root_path=root_path)

            files, errors = self._discover(root_path, recursive)
            candidates = self.detector.get_hash_candidates(files)
            self.tracker.set_hash_total(len(candidates))
            hash_errors = self._hash_candidates(files, candidates, workers)

            groups = self.detector.find_duplicates(files)
            stats = self.detector.summarize(groups)
            stats.update(total_files=len(files), total_bytes=total_size(files),
                         error_count=len(errors) + hash_errors)
            cancelled = self.cancel_event.is_set()
            status = "CANCELLED" if cancelled else "COMPLETED"

            # Related writes, one transaction: files + session totals succeed or fail together.
            with self.db.transaction() as cursor:
                self.file_repo.insert_files(scan_id, files, cursor=cursor)
                self.scan_repo.update_scan(scan_id, status, stats, cursor=cursor)

            summary = dict(stats, scan_id=scan_id, status=status, root_path=root_path)
            log.info("Scan %s %s: %s files, %s duplicate groups", scan_id, status,
                     stats["total_files"], stats["duplicate_groups"])
            self._emit(EventType.SCAN_CANCELLED if cancelled else EventType.SCAN_COMPLETED,
                       summary=summary)
        except Exception as exc:                                  # never let the thread die silently
            log.exception("Scan failed")
            if scan_id is not None:
                try:
                    self.scan_repo.update_scan(scan_id, "FAILED", {})
                except Exception:
                    log.exception("Could not mark scan %s as FAILED", scan_id)
            self._emit(EventType.SCAN_FAILED, scan_id=scan_id, message=str(exc))

    def _discover(self, root_path: str, recursive: bool):
        def on_progress(found: int, errors: int, current: str) -> None:
            self.tracker.set_discovered(found, errors)
            self._emit(EventType.DISCOVERY_PROGRESS, discovered=found, errors=errors, current=current)

        scanner = DirectoryScanner(excluded_dirs=[self.quarantine_dir], recursive=recursive,
                                   cancel_event=self.cancel_event, progress_callback=on_progress)
        result = scanner.scan_directory(root_path)
        self.tracker.set_discovered(len(result.files), result.error_count)
        self._emit(EventType.DISCOVERY_PROGRESS, discovered=len(result.files),
                   errors=result.error_count, current="Discovery finished")
        for message in result.errors[:50]:                        # do not flood the GUI
            self._emit(EventType.ERROR, message=message)
        return result.files, result.errors

    def _hash_candidates(self, files: List[Dict], candidates: List[Dict], workers: int) -> int:
        """Hash candidate files with a worker pool. Returns the number of hashing problems."""
        by_path = {f["absolute_path"]: f for f in files}
        hashed_paths = set()
        problems = 0

        if candidates and not self.cancel_event.is_set():
            executor = ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix="HashWorker")
            try:
                futures = {executor.submit(self.hasher.calculate_hash, f["absolute_path"],
                                           self.cancel_event): f for f in candidates}
                for future in as_completed(futures):
                    if self.cancel_event.is_set():
                        for pending in futures:                  # stop scheduling: cancel queued tasks
                            pending.cancel()
                    if future.cancelled():
                        continue
                    result = future.result()
                    if result["status"] == STATUS_CANCELLED:
                        continue
                    record = by_path[result["path"]]
                    record["sha256"] = result["sha256"]
                    record["scan_status"] = result["status"]
                    hashed_paths.add(result["path"])
                    failed = result["status"] != "OK"
                    if failed:
                        problems += 1
                        self._emit(EventType.ERROR, message=result["error"])
                    self.tracker.add_hashed(failed)
                    snap = self.tracker.snapshot()
                    self._emit(EventType.HASH_PROGRESS, hashed=snap["hashed"], total=snap["total"],
                               percent=self.tracker.percent(), errors=snap["errors"],
                               current=os.path.basename(result["path"]))
            finally:
                executor.shutdown(wait=True)                      # always clean up the pool

        candidate_paths = {c["absolute_path"] for c in candidates}
        for record in files:                                      # unfinished candidates -> SKIPPED
            record.setdefault("sha256", None)
            if record["absolute_path"] in hashed_paths:
                continue
            unfinished = record["absolute_path"] in candidate_paths
            record["scan_status"] = "SKIPPED" if unfinished else "OK"
        return problems
