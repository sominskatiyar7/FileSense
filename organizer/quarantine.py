"""QuarantineService: reversible alternative to deleting duplicates.

Files are MOVED to storage/quarantine/ under a unique name. The original path is kept
in MySQL (file_operations.source_path) so restore() can put the file back.
Nothing is ever permanently deleted.
"""
import os
import shutil
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from utils.logger import get_logger

log = get_logger("quarantine")


class QuarantineService:
    def __init__(self, op_repo, quarantine_dir) -> None:
        self.op_repo = op_repo
        self.quarantine_dir = str(quarantine_dir)

    def _quarantine_target(self, file_name: str) -> str:
        """Unique name = timestamp + random id + original name (no collisions possible)."""
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return os.path.join(self.quarantine_dir, f"{stamp}_{uuid.uuid4().hex[:8]}_{file_name}")

    def quarantine_files(self, scan_id: int, files: List[Dict]) -> List[Dict]:
        """`files` are scanned_files records (need absolute_path, file_name, file_id)."""
        os.makedirs(self.quarantine_dir, exist_ok=True)
        return [self._quarantine_one(scan_id, record) for record in files]

    def _quarantine_one(self, scan_id: int, record: Dict) -> Dict:
        source = record["absolute_path"]
        destination = self._quarantine_target(record["file_name"])
        operation_id = None
        try:
            operation_id = self.op_repo.create_operation(scan_id, record.get("file_id"),
                                                         "QUARANTINE", source, destination)
            if not os.path.isfile(source):
                raise FileNotFoundError("File no longer exists at its original location")
            shutil.move(source, destination)
            self.op_repo.update_status(operation_id, "SUCCESS")
            log.info("Quarantined %s -> %s", source, destination)
            return {"status": "SUCCESS", "source": source, "destination": destination, "message": ""}
        except Exception as exc:
            message = str(exc)
            log.error("Quarantine failed for %s: %s", source, message)
            if operation_id is not None:
                try:
                    self.op_repo.update_status(operation_id, "FAILED", message)
                except Exception:
                    log.exception("Could not record failure of operation %s", operation_id)
            return {"status": "FAILED", "source": source, "destination": destination, "message": message}

    def restore(self, quarantine_op: Dict, destination: Optional[str] = None) -> Dict:
        """Move a quarantined file back.

        quarantine_op: a row from OperationRepository.get_quarantined_files().
        destination:   None -> original path. If that path is taken the result status is
                       'CONFLICT' and NOTHING is moved: the GUI must then ask for another path.
        Returns {'status': 'SUCCESS'|'FAILED'|'CONFLICT', 'destination', 'message'}.
        """
        quarantined = quarantine_op["destination_path"]
        target = destination or quarantine_op["source_path"]

        if os.path.exists(target):
            return {"status": "CONFLICT", "destination": target,
                    "message": "A file already exists at the restore location"}

        operation_id = None
        try:
            operation_id = self.op_repo.create_operation(quarantine_op["scan_id"],
                                                         quarantine_op.get("file_id"), "RESTORE",
                                                         quarantined, target)
            if not os.path.isfile(quarantined):
                raise FileNotFoundError("Quarantined file is missing from the quarantine folder")
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.move(quarantined, target)
            self.op_repo.update_status(operation_id, "SUCCESS")
            log.info("Restored %s -> %s", quarantined, target)
            return {"status": "SUCCESS", "destination": target, "message": ""}
        except Exception as exc:
            message = str(exc)
            log.error("Restore failed for %s: %s", quarantined, message)
            if operation_id is not None:
                try:
                    self.op_repo.update_status(operation_id, "FAILED", message)
                except Exception:
                    log.exception("Could not record failure of operation %s", operation_id)
            return {"status": "FAILED", "destination": target, "message": message}


def reconcile_pending_operations(op_repo) -> int:
    """At startup: a PENDING row means the app stopped mid-operation. Decide what really happened.

    destination exists and source is gone  -> the move finished: SUCCESS
    otherwise                              -> FAILED (file is still where it was)
    """
    fixed = 0
    for op in op_repo.get_pending_operations():
        moved = os.path.exists(op["destination_path"]) and not os.path.exists(op["source_path"])
        if moved:
            op_repo.update_status(op["operation_id"], "SUCCESS")
        else:
            op_repo.update_status(op["operation_id"], "FAILED", "Interrupted before completion")
        fixed += 1
    return fixed
