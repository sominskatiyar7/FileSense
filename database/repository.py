"""Data-access layer: ALL SQL lives here (never in the GUI or business logic).

Three repositories, one per table. Every query is parameterized (%s placeholders)
so file paths can never break or inject into SQL.
Each write method accepts an optional `cursor` so several writes can share one
transaction (see DatabaseManager.transaction()).
"""
from contextlib import contextmanager
from datetime import datetime
from typing import Dict, Iterable, List, Optional

from database.connection import DatabaseManager


class BaseRepository:
    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    @contextmanager
    def _use(self, cursor=None, commit: bool = False):
        """Use the caller's cursor (shared transaction) or open our own."""
        if cursor is not None:
            yield cursor
        else:
            with self.db.cursor(commit=commit) as own:
                yield own


class ScanRepository(BaseRepository):
    """Table: scan_sessions"""

    def create_scan(self, root_path: str) -> int:
        with self._use(commit=True) as cur:
            cur.execute("INSERT INTO scan_sessions (root_path, status) VALUES (%s, 'RUNNING')",
                        (root_path,))
            return cur.lastrowid

    def update_scan(self, scan_id: int, status: str, stats: Optional[Dict] = None, cursor=None) -> None:
        stats = stats or {}
        with self._use(cursor, commit=True) as cur:
            cur.execute(
                """UPDATE scan_sessions
                   SET status=%s, completed_at=%s, total_files=%s, total_bytes=%s,
                       duplicate_groups=%s, duplicate_files=%s, reclaimable_bytes=%s, error_count=%s
                   WHERE scan_id=%s""",
                (status, datetime.now() if status != "RUNNING" else None,
                 stats.get("total_files", 0), stats.get("total_bytes", 0),
                 stats.get("duplicate_groups", 0), stats.get("duplicate_files", 0),
                 stats.get("reclaimable_bytes", 0), stats.get("error_count", 0), scan_id))

    def get_scan(self, scan_id: int) -> Optional[Dict]:
        with self._use() as cur:
            cur.execute("SELECT * FROM scan_sessions WHERE scan_id=%s", (scan_id,))
            return cur.fetchone()

    def get_scan_history(self, limit: int = 100) -> List[Dict]:
        with self._use() as cur:
            cur.execute("SELECT * FROM scan_sessions ORDER BY scan_id DESC LIMIT %s", (limit,))
            return cur.fetchall()

    def get_latest_scans_per_root(self) -> List[Dict]:
        """Newest COMPLETED scan of each folder (so re-scanning a folder is not double counted)."""
        with self._use() as cur:
            cur.execute(
                """SELECT s.* FROM scan_sessions s
                   JOIN (SELECT MAX(scan_id) AS max_id FROM scan_sessions
                         WHERE status='COMPLETED' GROUP BY root_path) latest
                     ON s.scan_id = latest.max_id""")
            return cur.fetchall()

    def mark_interrupted_scans(self) -> int:
        """A scan still RUNNING at startup was interrupted (crash/closed window): mark FAILED."""
        with self._use(commit=True) as cur:
            cur.execute("UPDATE scan_sessions SET status='FAILED', completed_at=NOW() "
                        "WHERE status='RUNNING'")
            return cur.rowcount


class FileRepository(BaseRepository):
    """Table: scanned_files"""

    _INSERT = ("INSERT INTO scanned_files (scan_id, absolute_path, file_name, extension, "
               "size_bytes, modified_at, sha256, scan_status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)")

    def insert_files(self, scan_id: int, files: Iterable[Dict], cursor=None, batch: int = 1000) -> int:
        rows = [(scan_id, f["absolute_path"], f["file_name"], f["extension"], f["size_bytes"],
                 f.get("modified_at"), f.get("sha256"), f.get("scan_status", "OK")) for f in files]
        with self._use(cursor, commit=True) as cur:
            for start in range(0, len(rows), batch):
                cur.executemany(self._INSERT, rows[start:start + batch])
        return len(rows)

    def get_files(self, scan_id: int, limit: Optional[int] = None) -> List[Dict]:
        sql = "SELECT * FROM scanned_files WHERE scan_id=%s ORDER BY size_bytes DESC, file_name"
        params = [scan_id]
        if limit:
            sql += " LIMIT %s"
            params.append(limit)
        with self._use() as cur:
            cur.execute(sql, tuple(params))
            return cur.fetchall()

    def get_duplicate_groups(self, scan_id: int) -> List[Dict]:
        with self._use() as cur:
            cur.execute(
                """SELECT size_bytes, sha256, COUNT(*) AS copies,
                          SUM(size_bytes) - MAX(size_bytes) AS reclaimable_bytes
                   FROM scanned_files
                   WHERE scan_id=%s AND sha256 IS NOT NULL AND scan_status='OK'
                   GROUP BY size_bytes, sha256
                   HAVING COUNT(*) > 1
                   ORDER BY reclaimable_bytes DESC""", (scan_id,))
            return cur.fetchall()

    def get_duplicate_files(self, scan_id: int) -> List[Dict]:
        """Every file that belongs to a duplicate group of this scan."""
        with self._use() as cur:
            cur.execute(
                """SELECT f.* FROM scanned_files f
                   JOIN (SELECT size_bytes, sha256 FROM scanned_files
                         WHERE scan_id=%s AND sha256 IS NOT NULL AND scan_status='OK'
                         GROUP BY size_bytes, sha256 HAVING COUNT(*) > 1) d
                     ON f.size_bytes = d.size_bytes AND f.sha256 = d.sha256
                   WHERE f.scan_id=%s AND f.scan_status='OK'
                   ORDER BY f.size_bytes DESC, f.sha256, f.absolute_path""", (scan_id, scan_id))
            return cur.fetchall()


class OperationRepository(BaseRepository):
    """Table: file_operations"""

    def create_operation(self, scan_id: int, file_id: Optional[int], operation_type: str,
                         source_path: str, destination_path: str) -> int:
        """Insert a PENDING record BEFORE touching the filesystem."""
        with self._use(commit=True) as cur:
            cur.execute(
                """INSERT INTO file_operations
                   (scan_id, file_id, operation_type, source_path, destination_path, status)
                   VALUES (%s,%s,%s,%s,%s,'PENDING')""",
                (scan_id, file_id, operation_type, source_path, destination_path))
            return cur.lastrowid

    def update_status(self, operation_id: int, status: str, error_message: Optional[str] = None) -> None:
        with self._use(commit=True) as cur:
            cur.execute("UPDATE file_operations SET status=%s, error_message=%s WHERE operation_id=%s",
                        (status, error_message, operation_id))

    def get_operations(self, scan_id: Optional[int] = None, limit: int = 200) -> List[Dict]:
        sql = "SELECT * FROM file_operations"
        params: list = []
        if scan_id is not None:
            sql += " WHERE scan_id=%s"
            params.append(scan_id)
        sql += " ORDER BY operation_id DESC LIMIT %s"
        params.append(limit)
        with self._use() as cur:
            cur.execute(sql, tuple(params))
            return cur.fetchall()

    def get_pending_operations(self) -> List[Dict]:
        with self._use() as cur:
            cur.execute("SELECT * FROM file_operations WHERE status='PENDING'")
            return cur.fetchall()

    def get_quarantined_files(self) -> List[Dict]:
        """Successful QUARANTINE operations that have not been restored yet."""
        with self._use() as cur:
            cur.execute(
                """SELECT q.* FROM file_operations q
                   WHERE q.operation_type='QUARANTINE' AND q.status='SUCCESS'
                     AND NOT EXISTS (SELECT 1 FROM file_operations r
                                     WHERE r.operation_type='RESTORE' AND r.status='SUCCESS'
                                       AND r.source_path = q.destination_path
                                       AND r.operation_id > q.operation_id)
                   ORDER BY q.operation_id DESC""")
            return cur.fetchall()

    def count_by_type_and_status(self) -> List[Dict]:
        with self._use() as cur:
            cur.execute("SELECT operation_type, status, COUNT(*) AS total "
                        "FROM file_operations GROUP BY operation_type, status")
            return cur.fetchall()
