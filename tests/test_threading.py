import ast
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from scanner.hashing import FileHasher
from scanner.scan_manager import ScanManager
from tests.fakes import FakeDatabase, FakeFileRepository, FakeScanRepository
from utils.progress import EventType

PROJECT = Path(__file__).resolve().parent.parent


class ScanManagerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "data"
        self.root.mkdir()
        self.scan_repo, self.file_repo = FakeScanRepository(), FakeFileRepository()
        self.manager = ScanManager(self.scan_repo, self.file_repo, FakeDatabase(),
                                   Path(self._tmp.name) / "quarantine", chunk_size=1024)

    def tearDown(self):
        self._tmp.cleanup()

    def _populate(self, count=30):
        for i in range(count):
            (self.root / f"f{i}.txt").write_bytes(b"same content" if i % 2 == 0 else f"unique {i}!".encode())

    def _drain(self):
        events = []
        while not self.manager.event_queue.empty():
            events.append(self.manager.event_queue.get_nowait())
        return events

    def test_multiple_files_hashed_and_events_generated(self):
        self._populate()
        self.manager.start_scan(str(self.root), workers=4)
        self.manager.wait(20)
        events = self._drain()
        types = [e.type for e in events]
        self.assertEqual(types[0], EventType.SCAN_STARTED)
        self.assertIn(EventType.DISCOVERY_PROGRESS, types)
        self.assertIn(EventType.HASH_PROGRESS, types)
        self.assertEqual(types[-1], EventType.SCAN_COMPLETED)
        summary = events[-1].data["summary"]
        self.assertEqual(summary["total_files"], 30)
        self.assertEqual(summary["duplicate_groups"], 1)
        self.assertEqual(summary["duplicate_files"], 15)
        self.assertEqual(self.scan_repo.scans[1]["status"], "COMPLETED")
        self.assertEqual(len(self.file_repo.saved[1]), 30)

    def test_hashing_runs_on_worker_threads_not_main(self):
        self._populate(10)
        names = set()
        original = FileHasher.calculate_hash

        def spy(hasher, path, cancel_event=None):
            names.add(threading.current_thread().name)
            return original(hasher, path, cancel_event)

        with mock.patch.object(FileHasher, "calculate_hash", spy):
            self.manager.start_scan(str(self.root), workers=3)
            self.manager.wait(20)
        self.assertTrue(names)
        self.assertTrue(all(n.startswith("HashWorker") for n in names), names)
        self.assertNotIn("MainThread", names)

    def test_cancellation_marks_scan_cancelled_and_keeps_results(self):
        self._populate(60)
        original = FileHasher.calculate_hash

        def slow(hasher, path, cancel_event=None):
            time.sleep(0.02)
            return original(hasher, path, cancel_event)

        with mock.patch.object(FileHasher, "calculate_hash", slow):
            self.manager.start_scan(str(self.root), workers=2)
            time.sleep(0.15)
            self.manager.cancel()
            self.manager.wait(20)
        events = self._drain()
        self.assertEqual(events[-1].type, EventType.SCAN_CANCELLED)
        self.assertEqual(self.scan_repo.scans[1]["status"], "CANCELLED")
        saved = self.file_repo.saved[1]
        self.assertEqual(len(saved), 60)                                  # nothing lost
        self.assertTrue(any(f["scan_status"] == "SKIPPED" for f in saved))  # unfinished ones marked

    def test_scan_failure_is_reported(self):
        self.scan_repo.create_scan = mock.Mock(side_effect=RuntimeError("db down"))
        self.manager.start_scan(str(self.root))
        self.manager.wait(10)
        self.assertEqual(self._drain()[-1].type, EventType.SCAN_FAILED)

    def test_second_scan_while_running_is_refused(self):
        self._populate(20)
        original = FileHasher.calculate_hash
        with mock.patch.object(FileHasher, "calculate_hash",
                               lambda h, p, c=None: (time.sleep(0.05), original(h, p, c))[1]):
            self.manager.start_scan(str(self.root), workers=1)
            with self.assertRaises(RuntimeError):
                self.manager.start_scan(str(self.root))
            self.manager.cancel()
            self.manager.wait(20)


class ArchitectureRuleTests(unittest.TestCase):
    """Static checks of the threading rules: they read the source code, nothing is executed."""

    @staticmethod
    def _imports(path: Path):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        found = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                found.add(node.module.split(".")[0])
        return found

    def test_worker_and_scanner_modules_never_import_tkinter(self):
        for folder in ("scanner", "organizer", "analytics", "database", "utils"):
            for path in (PROJECT / folder).glob("*.py"):
                self.assertNotIn("tkinter", self._imports(path), path.name)

    def test_hashing_module_does_not_touch_mysql(self):
        imports = self._imports(PROJECT / "scanner" / "hashing.py")
        self.assertFalse({"mysql", "database"} & imports)

    def test_gui_files_contain_no_sql(self):
        import re
        patterns = [r"\bSELECT\b[^\n]*\bFROM\b", r"\bINSERT INTO\b", r"\bDELETE FROM\b",
                    r"\bUPDATE\b\s+\w+\s+SET\b", r"\.execute\(", r"mysql\.connector"]
        for path in (PROJECT / "ui").glob("*.py"):
            text = path.read_text(encoding="utf-8")
            for pattern in patterns:
                self.assertIsNone(re.search(pattern, text), f"{path.name} contains SQL-like code: {pattern}")

    def test_hash_workers_share_no_database_connection(self):
        # Hash workers run FileHasher.calculate_hash only; DB writes happen in the coordinator.
        source = (PROJECT / "scanner" / "scan_manager.py").read_text(encoding="utf-8")
        self.assertIn("executor.submit(self.hasher.calculate_hash", source)
        self.assertNotIn("executor.submit(self.file_repo", source)
        self.assertNotIn("executor.submit(self.scan_repo", source)


if __name__ == "__main__":
    unittest.main()
