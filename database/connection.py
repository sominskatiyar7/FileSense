"""DatabaseManager: opens MySQL connections safely.

Every call to get_connection() returns a NEW connection. Connections are never
shared between threads, which keeps the hashing workers and the GUI safe.
"""
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional, Tuple

import mysql.connector
from mysql.connector import Error as MySQLError

from config import Settings
from utils.logger import get_logger

log = get_logger("database")

REQUIRED_TABLES = {"scan_sessions", "scanned_files", "file_operations"}


class DatabaseError(Exception):
    """Friendly database exception. `errno` holds the MySQL error number when known."""

    def __init__(self, message: str, errno: Optional[int] = None) -> None:
        super().__init__(message)
        self.errno = errno


class DatabaseManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    # ---- connections -------------------------------------------------
    def get_connection(self, use_database: bool = True):
        config = self.settings.db_config()
        if use_database:
            config["database"] = self.settings.db_name
        try:
            return mysql.connector.connect(connection_timeout=5, **config)
        except MySQLError as exc:
            log.error("MySQL connection failed: %s", exc.msg)
            raise DatabaseError(f"Could not connect to MySQL: {exc.msg}", exc.errno) from exc

    @contextmanager
    def cursor(self, commit: bool = False, dictionary: bool = True) -> Iterator:
        """Open a connection + cursor, always close them. Rolls back on error."""
        conn = self.get_connection()
        cur = conn.cursor(dictionary=dictionary)
        try:
            yield cur
            if commit:
                conn.commit()
        except MySQLError as exc:
            conn.rollback()
            log.error("SQL error, rolled back: %s", exc.msg)
            raise DatabaseError(f"Database error: {exc.msg}", exc.errno) from exc
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
            conn.close()

    @contextmanager
    def transaction(self) -> Iterator:
        """Several statements, one commit. Use when related changes must succeed together."""
        with self.cursor(commit=True) as cur:
            yield cur

    # ---- health / setup ---------------------------------------------
    def check_connection(self) -> Tuple[bool, str]:
        try:
            conn = self.get_connection()
            conn.close()
            return True, "Connected"
        except DatabaseError as exc:
            return False, str(exc)

    def missing_tables(self) -> set:
        with self.cursor() as cur:
            cur.execute("SHOW TABLES")
            existing = {list(row.values())[0].lower() for row in cur.fetchall()}
        return REQUIRED_TABLES - existing

    def initialize_schema(self, schema_path: Path) -> None:
        """Run the CREATE TABLE statements of schema.sql inside the existing database.

        CREATE DATABASE / USE lines are skipped on purpose: FileSense never creates
        databases with administrator credentials on its own.
        """
        text = Path(schema_path).read_text(encoding="utf-8")
        text = re.sub(r"--[^\n]*", "", text)            # strip SQL comments
        statements = [s.strip() for s in text.split(";") if s.strip()]
        with self.cursor(commit=True) as cur:
            for statement in statements:
                head = statement.upper()
                if head.startswith("CREATE DATABASE") or head.startswith("USE "):
                    continue
                cur.execute(statement)
        log.info("Database schema verified/created")
