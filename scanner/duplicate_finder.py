"""DuplicateDetector: exact-duplicate detection using size first, then SHA-256.

Names are NEVER used to decide that two files are duplicates.
"""
from typing import Dict, List

from analytics.analytics import sort_groups_by_reclaimable, total_reclaimable


class DuplicateDetector:
    @staticmethod
    def group_by_size(files: List[Dict]) -> Dict[int, List[Dict]]:
        groups: Dict[int, List[Dict]] = {}
        for record in files:
            groups.setdefault(record["size_bytes"], []).append(record)
        return groups

    def get_hash_candidates(self, files: List[Dict]) -> List[Dict]:
        """Steps 1-2: only files whose size occurs more than once need hashing."""
        by_size = self.group_by_size(files)
        return [f for group in by_size.values() if len(group) > 1 for f in group]

    @staticmethod
    def find_duplicates(files: List[Dict]) -> List[Dict]:
        """Steps 4-5: group hashed files by (size_bytes, sha256); keep groups with 2+ files.

        Each group is a dict: size_bytes, sha256, files, copies, reclaimable_bytes.
        reclaimable_bytes = (copies - 1) * size_bytes. Largest savings first.
        """
        buckets: Dict[tuple, List[Dict]] = {}
        for record in files:
            if record.get("sha256") and record.get("scan_status", "OK") == "OK":
                buckets.setdefault((record["size_bytes"], record["sha256"]), []).append(record)
        groups = []
        for (size, digest), members in buckets.items():
            if len(members) > 1:
                groups.append({"size_bytes": size, "sha256": digest, "files": members,
                               "copies": len(members),
                               "reclaimable_bytes": (len(members) - 1) * size})
        return sort_groups_by_reclaimable(groups)

    def summarize(self, groups: List[Dict]) -> Dict:
        return {"duplicate_groups": len(groups),
                "duplicate_files": sum(g["copies"] for g in groups),
                "reclaimable_bytes": total_reclaimable(groups)}
