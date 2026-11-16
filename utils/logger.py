"""Logging setup. Passwords are never logged (Settings hides them from repr)."""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

ROOT_LOGGER_NAME = "filesense"


def setup_logging(log_dir: Path) -> logging.Logger:
    """Create the log folder and attach file + console handlers (only once)."""
    logger = logging.getLogger(ROOT_LOGGER_NAME)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
    try:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            Path(log_dir) / "filesense.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError:
        pass  # logging to file is optional; console logging still works
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)
    return logger


def get_logger(name: str) -> logging.Logger:
    """Return a child logger such as 'filesense.scanner'."""
    return logging.getLogger(f"{ROOT_LOGGER_NAME}.{name}")
