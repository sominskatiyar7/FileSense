import tempfile
import unittest
from pathlib import Path
from unittest import mock

from organizer.quarantine import QuarantineService, reconcile_pending_operations
from tests.fakes import FakeOperationRepository


class QuarantineTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.qdir = self.root / "quarantine"
        self.work = self.root / "work"
        self.work.mkdir()
        self.ops = FakeOperationRepository()
        self.service = QuarantineService(self.ops, self.qdir)

    def tearDown(self):
        self._tmp.cleanup()

    def _quarantine(self, name="dup.txt", content=b"copy"):
        path = self.work / name
        path.write_bytes(content)
        result = self.service.quarantine_files(1, [{"file_id": None, "file_name": name,
                                                   "absolute_path": str(path)}])[0]
        return path, result

    def test_successful_quarantine(self):
        path, result = self._quarantine()
        self.assertEqual(result["status"], "SUCCESS")
        self.assertFalse(path.exists())
        self.assertTrue(Path(result["destination"]).exists())
        self.assertEqual(self.ops.by_type("QUARANTINE")[0]["source_path"], str(path))

    def test_same_name_files_do_not_collide(self):
        _, first = self._quarantine("same.txt", b"1")
        _, second = self._quarantine("same.txt", b"2")
        self.assertNotEqual(first["destination"], second["destination"])

    def test_successful_restore(self):
        path, _ = self._quarantine()
        op = self.ops.by_type("QUARANTINE")[0]
        result = self.service.restore(op)
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(path.read_bytes(), b"copy")
        self.assertEqual(self.ops.by_type("RESTORE")[0]["status"], "SUCCESS")

    def test_restore_conflict_does_not_overwrite(self):
        path, _ = self._quarantine()
        path.write_bytes(b"NEW FILE")                       # someone created a file at the old path
        op = self.ops.by_type("QUARANTINE")[0]
        result = self.service.restore(op)
        self.assertEqual(result["status"], "CONFLICT")
        self.assertEqual(path.read_bytes(), b"NEW FILE")
        self.assertTrue(Path(op["destination_path"]).exists())
        # ...and restoring to a different path works
        other = str(self.work / "restored.txt")
        self.assertEqual(self.service.restore(op, other)["status"], "SUCCESS")
        self.assertEqual(Path(other).read_bytes(), b"copy")

    def test_missing_quarantined_file(self):
        self._quarantine()
        op = self.ops.by_type("QUARANTINE")[0]
        Path(op["destination_path"]).unlink()
        result = self.service.restore(op)
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(self.ops.by_type("RESTORE")[0]["status"], "FAILED")

    def test_failed_quarantine_move_keeps_file(self):
        path = self.work / "a.txt"
        path.write_bytes(b"x")
        with mock.patch("organizer.quarantine.shutil.move", side_effect=OSError("disk error")):
            result = self.service.quarantine_files(1, [{"file_id": None, "file_name": "a.txt",
                                                        "absolute_path": str(path)}])[0]
        self.assertEqual(result["status"], "FAILED")
        self.assertTrue(path.exists())
        self.assertEqual(self.ops.by_type("QUARANTINE")[0]["status"], "FAILED")

    def test_missing_source_file_fails_cleanly(self):
        result = self.service.quarantine_files(1, [{"file_id": None, "file_name": "x.txt",
                                                    "absolute_path": str(self.work / "x.txt")}])[0]
        self.assertEqual(result["status"], "FAILED")

    def test_reconcile_pending_operations(self):
        done_src, done_dst = self.work / "s1", self.work / "d1"
        done_dst.write_bytes(b"x")                          # move finished, but status never updated
        a = self.ops.create_operation(1, None, "ORGANIZE", str(done_src), str(done_dst))
        stuck_src = self.work / "s2"
        stuck_src.write_bytes(b"y")                         # move never happened
        b = self.ops.create_operation(1, None, "ORGANIZE", str(stuck_src), str(self.work / "d2"))

        class Repo:                                         # adapt the fake to the pending-ops API
            def get_pending_operations(s): return [r for r in self.ops.rows.values() if r["status"] == "PENDING"]
            def update_status(s, *args): self.ops.update_status(*args)

        self.assertEqual(reconcile_pending_operations(Repo()), 2)
        self.assertEqual(self.ops.rows[a]["status"], "SUCCESS")
        self.assertEqual(self.ops.rows[b]["status"], "FAILED")


if __name__ == "__main__":
    unittest.main()
