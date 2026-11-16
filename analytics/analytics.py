"""Analytics: totals, filters and sorting helpers.

This module is where lambda, filter() and functools.reduce() are used for real:
  * reduce  -> add up sizes / reclaimable bytes
  * filter  -> pick PDFs, large files, duplicates, files of one category
  * lambda  -> sort keys
"""
from functools import reduce
from typing import Callable, Dict, List

from organizer.file_categories import FileCategorizer


# ---------------------------------------------------------------- reduce ----
def total_size(files: List[Dict]) -> int:
    """Total bytes of a list of file records (reduce)."""
    return reduce(lambda running_total, f: running_total + f["size_bytes"], files, 0)


def total_reclaimable(groups: List[Dict]) -> int:
    """Total potentially reclaimable bytes over duplicate groups (reduce)."""
    return reduce(lambda running_total, g: running_total + g["reclaimable_bytes"], groups, 0)


# ---------------------------------------------------------------- filter ----
def filter_pdfs(files: List[Dict]) -> List[Dict]:
    return list(filter(lambda f: f["extension"].lower() == ".pdf", files))


def filter_large(files: List[Dict], min_bytes: int) -> List[Dict]:
    return list(filter(lambda f: f["size_bytes"] >= min_bytes, files))


def filter_duplicates(files: List[Dict], duplicate_hashes: set) -> List[Dict]:
    """Keep only files whose (size, sha256) pair is in `duplicate_hashes`."""
    return list(filter(lambda f: (f["size_bytes"], f.get("sha256")) in duplicate_hashes, files))


def filter_by_category(files: List[Dict], category: str, categorizer: FileCategorizer) -> List[Dict]:
    return list(filter(lambda f: categorizer.get_category(f["file_name"]) == category, files))


# ---------------------------------------------------------------- lambda ----
def sort_by_size(files: List[Dict], largest_first: bool = True) -> List[Dict]:
    return sorted(files, key=lambda f: f["size_bytes"], reverse=largest_first)


def sort_by_name(files: List[Dict]) -> List[Dict]:
    return sorted(files, key=lambda f: f["file_name"].lower())


def sort_groups_by_reclaimable(groups: List[Dict]) -> List[Dict]:
    return sorted(groups, key=lambda g: g["reclaimable_bytes"], reverse=True)


class AnalyticsService:
    """Builds the dashboard numbers from real MySQL data."""

    def __init__(self, scan_repo, op_repo) -> None:
        self.scan_repo = scan_repo
        self.op_repo = op_repo

    def get_dashboard_stats(self) -> Dict:
        """Totals use the newest completed scan of every scanned folder."""
        latest = self.scan_repo.get_latest_scans_per_root()
        add = lambda key: reduce(lambda acc, s: acc + (s[key] or 0), latest, 0)  # noqa: E731
        counts = self.get_operation_counts()
        return {
            "total_files": add("total_files"),
            "total_bytes": add("total_bytes"),
            "duplicate_groups": add("duplicate_groups"),
            "duplicate_files": add("duplicate_files"),
            "reclaimable_bytes": add("reclaimable_bytes"),
            "organized_files": counts["ORGANIZE"],
            "quarantined_files": counts["QUARANTINE"],
            "restored_files": counts["RESTORE"],
            "scans_run": len(self.scan_repo.get_scan_history(limit=100000)),
            "recent_scans": self.scan_repo.get_scan_history(limit=5),
            "recent_operations": self.op_repo.get_operations(limit=8),
        }

    def get_operation_counts(self) -> Dict[str, int]:
        """Successful operations per type."""
        counts = {"ORGANIZE": 0, "QUARANTINE": 0, "RESTORE": 0}
        for row in self.op_repo.count_by_type_and_status():
            if row["status"] == "SUCCESS":
                counts[row["operation_type"]] = int(row["total"])
        return counts

    def get_scan_history_stats(self) -> Dict:
        history = self.scan_repo.get_scan_history(limit=100000)
        by_status: Dict[str, int] = {}
        for scan in history:
            by_status[scan["status"]] = by_status.get(scan["status"], 0) + 1
        return {"total_scans": len(history), "by_status": by_status}
