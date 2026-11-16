"""Integration tests: need a REAL MySQL TEST database. Skipped unless it is configured.

Windows CMD:
    set FILESENSE_TEST_DB=filesense_test_db
    set FILESENSE_DB_USER=root
    set FILESENSE_DB_PASSWORD=...
    python -m unittest tests.test_database_integration
(create the empty database first:  CREATE DATABASE filesense_test_db;)
Never point this at your real filesense_db: the tests insert and delete rows.
"""
import os
import tempfile
import unittest
from pathlib import Path

from config import SCHEMA_FILE, load_settings

TEST_DB = os.environ.get("FILESENSE_TEST_DB")


@unittest.skipUnless(TEST_DB, "set FILESENSE_TEST_DB to run database integration tests")
class DatabaseIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from analytics.analytics import AnalyticsService
        from database.connection import DatabaseManager
        from database.repository import FileRepository, OperationRepository, ScanRepository
        from organizer.quarantine import QuarantineService
        from scanner.scan_manager import ScanManager
        settings = load_settings()
        settings.db_name = TEST_DB
        cls.settings = settings
        cls.db = DatabaseManager(settings)
        cls.db.initialize_schema(SCHEMA_FILE)
        cls.scans, cls.files, cls.ops = ScanRepository(cls.db), FileRepository(cls.db), OperationRepository(cls.db)
        cls.AnalyticsService, cls.ScanManager, cls.QuarantineService = AnalyticsService, ScanManager, QuarantineService

    def setUp(self):
        with self.db.cursor(commit=True) as cur:
            cur.execute("DELETE FROM file_operations")
            cur.execute("DELETE FROM scanned_files")
            cur.execute("DELETE FROM scan_sessions")
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "data"
        self.root.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_full_scan_quarantine_restore_flow(self):
        (self.root / "a.txt").write_bytes(b"duplicate")
        (self.root / "b.txt").write_bytes(b"duplicate")
        (self.root / "c.txt").write_bytes(b"other!!!!")
        manager = self.ScanManager(self.scans, self.files, self.db, Path(self._tmp.name) / "q", 1024)
        manager.start_scan(str(self.root), workers=2)
        manager.wait(30)
        scan = self.scans.get_scan_history(1)[0]
        self.assertEqual(scan["status"], "COMPLETED")
        self.assertEqual((scan["total_files"], scan["duplicate_groups"], scan["duplicate_files"]), (3, 1, 2))
        self.assertEqual(scan["reclaimable_bytes"], 9)

        groups = self.files.get_duplicate_groups(scan["scan_id"])
        self.assertEqual(groups[0]["copies"], 2)
        dups = self.files.get_duplicate_files(scan["scan_id"])
        self.assertEqual(len(dups), 2)

        service = self.QuarantineService(self.ops, Path(self._tmp.name) / "q")
        results = service.quarantine_files(scan["scan_id"], dups[:1])
        self.assertEqual(results[0]["status"], "SUCCESS")
        quarantined = self.ops.get_quarantined_files()
        self.assertEqual(len(quarantined), 1)

        stats = self.AnalyticsService(self.scans, self.ops).get_dashboard_stats()
        self.assertEqual(stats["quarantined_files"], 1)
        self.assertEqual(stats["total_files"], 3)

        self.assertEqual(service.restore(quarantined[0])["status"], "SUCCESS")
        self.assertEqual(self.ops.get_quarantined_files(), [])
        self.assertEqual(self.AnalyticsService(self.scans, self.ops).get_operation_counts()["RESTORE"], 1)

    def test_paths_with_quotes_are_safe(self):
        scan_id = self.scans.create_scan("C:\\weird'; DROP TABLE scan_sessions; --")
        self.assertEqual(self.scans.get_scan(scan_id)["root_path"], "C:\\weird'; DROP TABLE scan_sessions; --")


if __name__ == "__main__":
    unittest.main()
