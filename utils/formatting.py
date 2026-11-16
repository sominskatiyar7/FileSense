"""Small reusable helpers that turn raw values into readable text."""
from datetime import datetime
from typing import Optional

_UNITS = ["B", "KB", "MB", "GB", "TB"]


def format_size(num_bytes: Optional[int]) -> str:
    """1536 -> '1.50 KB'. Uses 1024-based units."""
    if num_bytes is None:
        return "-"
    size = float(num_bytes)
    for unit in _UNITS:
        if size < 1024 or unit == _UNITS[-1]:
            return f"{int(size)} B" if unit == "B" else f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"


def format_timestamp(value: Optional[datetime]) -> str:
    """datetime -> '2026-11-15 14:30:00' (or '-' when missing)."""
    if value is None:
        return "-"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def format_status(status: Optional[str]) -> str:
    """'ROLLED_BACK' -> 'Rolled Back'."""
    if not status:
        return "-"
    return str(status).replace("_", " ").title()


def short_hash(sha256: Optional[str], length: int = 12) -> str:
    """Shortened hash for display in tables."""
    return f"{sha256[:length]}..." if sha256 else "-"
