import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scanner.discovery import DirectoryScanner


def make_file(path: Path, content: bytes = b"data") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


class ScannerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_scan_folder_with_files(self):
        make_file(self.root / "a.txt", b"hello")
        make_file(self.root / "b.pdf", b"world!")
        result = DirectoryScanner().scan_directory(str(self.root))
        self.assertEqual(sorted(f["file_name"] for f in result.files), ["a.txt", "b.pdf"])
        sizes = {f["file_name"]: f["size_bytes"] for f in result.files}
        self.assertEqual(sizes, {"a.txt": 5, "b.pdf": 6})
        self.assertEqual(result.error_count, 0)

    def test_scan_empty_folder(self):
        result = DirectoryScanner().scan_directory(str(self.root))
        self.assertEqual(result.files, [])

    def test_scan_nested_folders(self):
        make_file(self.root / "one" / "two" / "deep.txt")
        make_file(self.root / "top.txt")
        self.assertEqual(len(DirectoryScanner().scan_directory(str(self.root)).files), 2)
        self.assertEqual(len(DirectoryScanner(recursive=False).scan_directory(str(self.root)).files), 1)

    def test_inaccessible_folder_is_reported_not_fatal(self):
        make_file(self.root / "ok.txt")
        make_file(self.root / "locked" / "secret.txt")
        real_scandir = os.scandir

        def fake_scandir(path):
            if os.path.basename(str(path)) == "locked":
                raise PermissionError(13, "Permission denied")
            return real_scandir(path)

        with mock.patch("scanner.discovery.os.scandir", side_effect=fake_scandir):
            result = DirectoryScanner().scan_directory(str(self.root))
        self.assertEqual([f["file_name"] for f in result.files], ["ok.txt"])
        self.assertEqual(result.error_count, 1)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks not supported")
    def test_symlinks_are_skipped(self):
        target = make_file(self.root / "real.txt")
        try:
            os.symlink(target, self.root / "link.txt")
        except (OSError, NotImplementedError):
            self.skipTest("cannot create symlinks here")
        names = [f["file_name"] for f in DirectoryScanner().scan_directory(str(self.root)).files]
        self.assertEqual(names, ["real.txt"])

    def test_excluded_directory_is_not_scanned(self):
        make_file(self.root / "keep.txt")
        make_file(self.root / "quarantine" / "hidden.txt")
        scanner = DirectoryScanner(excluded_dirs=[self.root / "quarantine"])
        names = [f["file_name"] for f in scanner.scan_directory(str(self.root)).files]
        self.assertEqual(names, ["keep.txt"])


if __name__ == "__main__":
    unittest.main()
