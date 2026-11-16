import tempfile
import unittest
from pathlib import Path
from unittest import mock

from organizer.file_categories import FileCategorizer
from organizer.organizer import OrganizerService
from tests.fakes import FakeOperationRepository


class CategorizerTests(unittest.TestCase):
    def test_known_extensions(self):
        c = FileCategorizer()
        self.assertEqual(c.get_category("report.PDF"), "Documents")
        self.assertEqual(c.get_category("photo.jpg"), "Images")
        self.assertEqual(c.get_category("song.mp3"), "Audio")
        self.assertEqual(c.get_category("main.py"), "Code")

    def test_unknown_and_missing_extension(self):
        c = FileCategorizer()
        self.assertEqual(c.get_category("data.xyz"), "Others")
        self.assertEqual(c.get_category("Makefile"), "Others")


class OrganizerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.ops = FakeOperationRepository()
        self.service = OrganizerService(self.ops)

    def tearDown(self):
        self._tmp.cleanup()

    def _record(self, name, content=b"x"):
        path = self.root / name
        path.write_bytes(content)
        return {"file_id": None, "file_name": name, "absolute_path": str(path)}

    def test_preview_does_not_move_anything(self):
        rec = self._record("report.pdf")
        plans = self.service.build_preview([rec], str(self.root))
        self.assertEqual(plans[0]["destination"], str(self.root / "Documents" / "report.pdf"))
        self.assertTrue((self.root / "report.pdf").exists())

    def test_successful_move_is_recorded(self):
        rec = self._record("photo.jpg")
        plans = self.service.build_preview([rec], str(self.root))
        results = self.service.execute(1, plans)
        self.assertEqual(results[0]["status"], "SUCCESS")
        self.assertTrue((self.root / "Images" / "photo.jpg").exists())
        self.assertFalse((self.root / "photo.jpg").exists())
        self.assertEqual(self.ops.by_type("ORGANIZE")[0]["status"], "SUCCESS")

    def test_existing_destination_is_never_overwritten(self):
        (self.root / "Documents").mkdir()
        (self.root / "Documents" / "report.pdf").write_bytes(b"ORIGINAL")
        rec = self._record("report.pdf", b"NEW")
        plans = self.service.build_preview([rec], str(self.root))
        self.assertEqual(Path(plans[0]["destination"]).name, "report (1).pdf")
        self.service.execute(1, plans)
        self.assertEqual((self.root / "Documents" / "report.pdf").read_bytes(), b"ORIGINAL")
        self.assertEqual((self.root / "Documents" / "report (1).pdf").read_bytes(), b"NEW")

    def test_failed_move_marked_failed_and_file_untouched(self):
        rec = self._record("a.txt")
        plans = self.service.build_preview([rec], str(self.root))
        with mock.patch("organizer.organizer.shutil.move", side_effect=PermissionError("denied")):
            results = self.service.execute(1, plans)
        self.assertEqual(results[0]["status"], "FAILED")
        self.assertEqual(self.ops.by_type("ORGANIZE")[0]["status"], "FAILED")
        self.assertIn("denied", self.ops.by_type("ORGANIZE")[0]["error_message"])
        self.assertTrue((self.root / "a.txt").exists())

    def test_category_filter(self):
        recs = [self._record("a.pdf"), self._record("b.jpg")]
        plans = self.service.build_preview(recs, str(self.root), "Images")
        self.assertEqual([p["file_name"] for p in plans], ["b.jpg"])

    def test_missing_source_is_skipped_in_preview(self):
        rec = self._record("gone.txt")
        (self.root / "gone.txt").unlink()
        self.assertEqual(self.service.build_preview([rec], str(self.root)), [])


if __name__ == "__main__":
    unittest.main()
