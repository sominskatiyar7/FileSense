"""Central configuration for FileSense.

Database credentials are read from environment variables so that no real
password is ever stored in the source code or pushed to GitHub.

Windows CMD example (before running main.py):
    set FILESENSE_DB_USER=root
    set FILESENSE_DB_PASSWORD=your_password_here
"""
import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SCHEMA_FILE = BASE_DIR / "database" / "schema.sql"

APP_NAME = "FileSense"
APP_TITLE = "Intelligent File Organizer and Duplicate Detection System"
APP_VERSION = "1.0.0"

# Category name -> list of extensions (lower case, with dot).
# Anything not listed here is placed in "Others".
FILE_CATEGORIES = {
    "Documents": [".pdf", ".doc", ".docx", ".txt", ".ppt", ".pptx", ".xls", ".xlsx"],
    "Images": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp"],
    "Videos": [".mp4", ".mkv", ".avi", ".mov"],
    "Audio": [".mp3", ".wav", ".aac", ".flac"],
    "Archives": [".zip", ".rar", ".7z", ".tar", ".gz"],
    "Code": [".py", ".java", ".c", ".cpp", ".js", ".html", ".css", ".sql"],
}
DEFAULT_CATEGORY = "Others"

HASH_CHUNK_SIZE = 1024 * 1024        # 1 MB per read
DEFAULT_HASH_WORKERS = 4
MIN_HASH_WORKERS = 1
MAX_HASH_WORKERS = 16
MAX_PATH_LENGTH = 1024               # matches VARCHAR(1024) in the schema


@dataclass
class Settings:
    """Runtime settings. The password is hidden from repr() so it cannot leak into logs."""
    db_host: str = "localhost"
    db_port: int = 3306
    db_name: str = "filesense_db"
    db_user: str = "root"
    db_password: str = field(default="", repr=False)
    hash_workers: int = DEFAULT_HASH_WORKERS
    chunk_size: int = HASH_CHUNK_SIZE
    quarantine_dir: Path = BASE_DIR / "storage" / "quarantine"
    log_dir: Path = BASE_DIR / "logs"

    def db_config(self) -> dict:
        """Keyword arguments for mysql.connector.connect()."""
        return {
            "host": self.db_host,
            "port": self.db_port,
            "user": self.db_user,
            "password": self.db_password,
        }


def load_settings() -> Settings:
    """Build Settings from environment variables, falling back to defaults."""
    return Settings(
        db_host=os.environ.get("FILESENSE_DB_HOST", "localhost"),
        db_port=int(os.environ.get("FILESENSE_DB_PORT", "3306")),
        db_name=os.environ.get("FILESENSE_DB_NAME", "filesense_db"),
        db_user=os.environ.get("FILESENSE_DB_USER", "root"),
        db_password=os.environ.get("FILESENSE_DB_PASSWORD", ""),
        hash_workers=int(os.environ.get("FILESENSE_HASH_WORKERS", DEFAULT_HASH_WORKERS)),
    )
