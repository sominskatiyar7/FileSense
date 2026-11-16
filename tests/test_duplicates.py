import tempfile
import unittest
from pathlib import Path

from scanner.discovery import DirectoryScanner
from scanner.duplicate_finder import DuplicateDetector
from scanner.hashing import FileHasher


class DuplicateTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.detector = DuplicateDetector()

    def tearDown(self):
        self._tmp.cleanup()

    def _pipeline(self, contents):
        """Create files {name: bytes}, then run discovery -> hashing -> duplicate detection."""
        for name, data in contents.items():
            (self.root / name).write_bytes(data)
        files = DirectoryScanner().scan_directory(str(self.root)).files
        hasher = FileHasher()
        for record in self.detector.get_hash_candidates(files):
            result = hasher.calculate_hash(record["absolute_path"])
            record["sha256"], record["scan_status"] = result["sha256"], result["status"]
        return self.detector.find_duplicates(files), files

    def test_two_identical_files(self):
        groups, _ = self._pipeline({"a.txt": b"same", "b.txt": b"same"})
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["copies"], 2)
        self.assertEqual(groups[0]["reclaimable_bytes"], 4)

    def test_three_identical_files(self):
        groups, _ = self._pipeline({"a": b"12345", "b": b"12345", "c": b"12345"})
        self.assertEqual(groups[0]["copies"], 3)
        self.assertEqual(groups[0]["reclaimable_bytes"], 10)      # (3 - 1) * 5

    def test_same_size_different_content_is_not_duplicate(self):
        groups, files = self._pipeline({"a": b"aaaa", "b": b"bbbb"})
        self.assertEqual(groups, [])
        self.assertEqual(len(self.detector.get_hash_candidates(files)), 2)   # hashed, but differ

    def test_different_sizes_are_never_hashed(self):
        groups, files = self._pipeline({"a": b"1", "b": b"22", "c": b"333"})
        self.assertEqual(groups, [])
        self.assertEqual(self.detector.get_hash_candidates(files), [])

    def test_no_duplicates_in_empty_list(self):
        self.assertEqual(self.detector.find_duplicates([]), [])

    def test_same_name_different_content_not_duplicate(self):
        (self.root / "x").mkdir()
        (self.root / "y").mkdir()
        (self.root / "x" / "report.pdf").write_bytes(b"one!")
        (self.root / "y" / "report.pdf").write_bytes(b"two!")
        files = DirectoryScanner().scan_directory(str(self.root)).files
        hasher = FileHasher()
        for record in files:
            record["sha256"] = hasher.calculate_hash(record["absolute_path"])["sha256"]
        self.assertEqual(self.detector.find_duplicates(files), [])

    def test_groups_sorted_by_reclaimable_and_summary(self):
        groups, _ = self._pipeline({"s1": b"ab", "s2": b"ab", "b1": b"x" * 100, "b2": b"x" * 100})
        self.assertEqual([g["size_bytes"] for g in groups], [100, 2])
        summary = self.detector.summarize(groups)
        self.assertEqual(summary, {"duplicate_groups": 2, "duplicate_files": 4, "reclaimable_bytes": 102})


if __name__ == "__main__":
    unittest.main()
