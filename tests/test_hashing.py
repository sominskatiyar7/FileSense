import hashlib
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from scanner.hashing import FileHasher


class HashingTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.hasher = FileHasher(chunk_size=1024)

    def tearDown(self):
        self._tmp.cleanup()

    def _file(self, name, content):
        path = self.root / name
        path.write_bytes(content)
        return str(path)

    def test_same_content_same_hash(self):
        a, b = self._file("a.bin", b"abc"), self._file("b.bin", b"abc")
        ha, hb = self.hasher.calculate_hash(a), self.hasher.calculate_hash(b)
        self.assertEqual(ha["sha256"], hb["sha256"])
        self.assertEqual(len(ha["sha256"]), 64)
        self.assertEqual(ha["sha256"], hashlib.sha256(b"abc").hexdigest())

    def test_different_content_different_hash(self):
        a, b = self._file("a.bin", b"abc"), self._file("b.bin", b"abd")
        self.assertNotEqual(self.hasher.calculate_hash(a)["sha256"], self.hasher.calculate_hash(b)["sha256"])

    def test_empty_file(self):
        result = self.hasher.calculate_hash(self._file("empty.bin", b""))
        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["sha256"], hashlib.sha256(b"").hexdigest())

    def test_large_file_read_in_chunks(self):
        content = b"x" * (5 * 1024 * 1024 + 123)            # many 1 KB chunks
        result = self.hasher.calculate_hash(self._file("big.bin", content))
        self.assertEqual(result["sha256"], hashlib.sha256(content).hexdigest())

    def test_missing_file_is_unreadable(self):
        result = self.hasher.calculate_hash(str(self.root / "nope.bin"))
        self.assertEqual(result["status"], "UNREADABLE")
        self.assertIsNone(result["sha256"])

    def test_file_changed_while_hashing(self):
        path = self._file("a.bin", b"abc")
        with mock.patch.object(FileHasher, "_snapshot", side_effect=[(3, 1), (3, 2)]):
            result = self.hasher.calculate_hash(path)
        self.assertEqual(result["status"], "CHANGED")
        self.assertIsNone(result["sha256"])

    def test_cancel_stops_hashing(self):
        event = threading.Event()
        event.set()
        result = self.hasher.calculate_hash(self._file("a.bin", b"abc"), event)
        self.assertEqual(result["status"], "CANCELLED")


if __name__ == "__main__":
    unittest.main()
