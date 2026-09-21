"""Rotating file logging shared by the app's modules: logs/<app>.log (gitignored)."""
import logging
import logging.handlers
import os
from pathlib import Path

LOG_DIR = Path(__file__).parent / "logs"


def setup_logging(app_name, level=None):
    """Attach a rotating file handler (1 MB x 3 backups) to the root logger.
    Level defaults to INFO; set APP_LOG_LEVEL=DEBUG to see best-effort failures
    that are deliberately swallowed. Safe to call more than once. If the log file can't be opened the app still
    runs - logging must never be the reason it fails to start."""
    root = logging.getLogger()
    if any(getattr(h, "_applog", False) for h in root.handlers):
        return
    try:
        LOG_DIR.mkdir(exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            LOG_DIR / f"{app_name}.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
    except OSError:
        return
    handler._applog = True
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)
    root.setLevel(level or os.environ.get("APP_LOG_LEVEL", "INFO").upper())
