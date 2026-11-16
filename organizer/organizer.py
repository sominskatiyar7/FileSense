"""OrganizerService: moves files into category folders (Documents/, Images/, ...).

Flow: build_preview() -> GUI asks the user to confirm -> execute().
Every move is logged: PENDING row first, then the real move, then SUCCESS or FAILED.
Existing files are never overwritten: a unique name such as "report (1).pdf" is used.
"""
import os
import shutil
from typing import Dict, List, Optional

from organizer.file_categories import FileCategorizer
from utils.logger import get_logger

log = get_logger("organizer")


def unique_path(path: str, reserved: Optional[set] = None) -> str:
    """Return `path`, or 'name (1).ext', 'name (2).ext'... until it neither exists nor is reserved."""
    reserved = reserved or set()
    base, ext = os.path.splitext(path)
    candidate, counter = path, 1
    while os.path.exists(candidate) or os.path.normcase(candidate) in reserved:
        candidate = f"{base} ({counter}){ext}"
        counter += 1
    return candidate


class OrganizerService:
    def __init__(self, op_repo, categorizer: Optional[FileCategorizer] = None,
                 quarantine_dir: Optional[str] = None) -> None:
        self.op_repo = op_repo
        self.categorizer = categorizer or FileCategorizer()
        self.quarantine_dir = os.path.normcase(os.path.abspath(str(quarantine_dir))) if quarantine_dir else None

    def _in_quarantine(self, path: str) -> bool:
        if not self.quarantine_dir:
            return False
        return os.path.normcase(os.path.abspath(path)).startswith(self.quarantine_dir + os.sep)

    def build_preview(self, files: List[Dict], root_path: str,
                      category_filter: Optional[str] = None) -> List[Dict]:
        """Nothing is moved here. Returns plans: file_id, source, destination, category, file_name."""
        plans: List[Dict] = []
        reserved: set = set()
        for record in files:
            source = record["absolute_path"]
            category = self.categorizer.get_category(record["file_name"])
            if category_filter and category_filter != "All" and category != category_filter:
                continue
            if self._in_quarantine(source) or not os.path.isfile(source):
                continue                                   # missing or protected file
            target_dir = os.path.join(root_path, category)
            if os.path.normcase(os.path.dirname(source)) == os.path.normcase(target_dir):
                continue                                   # already organized
            destination = unique_path(os.path.join(target_dir, record["file_name"]), reserved)
            reserved.add(os.path.normcase(destination))
            plans.append({"file_id": record.get("file_id"), "file_name": record["file_name"],
                          "category": category, "source": source, "destination": destination})
        return plans

    def execute(self, scan_id: int, plans: List[Dict]) -> List[Dict]:
        """Move files. Call only AFTER the user confirmed the preview."""
        results = []
        for plan in plans:
            results.append(self._move_one(scan_id, plan))
        return results

    def _move_one(self, scan_id: int, plan: Dict) -> Dict:
        source, destination = plan["source"], plan["destination"]
        operation_id = None
        try:
            operation_id = self.op_repo.create_operation(scan_id, plan.get("file_id"), "ORGANIZE",
                                                         source, destination)
            if not os.path.isfile(source):
                raise FileNotFoundError("Source file no longer exists")
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            if os.path.exists(destination):                # re-check: never overwrite
                destination = unique_path(destination)
            shutil.move(source, destination)
            self.op_repo.update_status(operation_id, "SUCCESS")
            log.info("Organized %s -> %s", source, destination)
            return {"status": "SUCCESS", "source": source, "destination": destination, "message": ""}
        except Exception as exc:
            message = str(exc)
            log.error("Organize failed for %s: %s", source, message)
            if operation_id is not None:
                try:
                    self.op_repo.update_status(operation_id, "FAILED", message)
                except Exception:
                    log.exception("Could not record failure of operation %s", operation_id)
            return {"status": "FAILED", "source": source, "destination": destination, "message": message}
