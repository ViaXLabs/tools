"""
Logging setup for the toolkit.

Every command gets its own timestamped log file under outputs/logs/, in
addition to console output. API keys are redacted from anything logged.
"""
from __future__ import annotations

import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

OUTPUTS_DIR = Path(os.environ.get("NR_TOOL_OUTPUTS_DIR", "outputs")).resolve()
LOG_DIR = OUTPUTS_DIR / "logs"
REPORT_DIR = OUTPUTS_DIR / "reports"
DATA_DIR = OUTPUTS_DIR / "data"
CHANGES_DIR = OUTPUTS_DIR / "changes"

_REDACT_PATTERNS = [
    re.compile(r"(Api-Key['\"]?\s*[:=]\s*['\"]?)([A-Za-z0-9._-]{8,})", re.IGNORECASE),
    re.compile(r"(NRAK-[A-Z0-9]{20,})"),  # New Relic user API key prefix
    re.compile(r"(NRAA-[A-Za-z0-9]{20,})"),  # New Relic account/ingest key prefix
]


def redact(text: str) -> str:
    """Strip anything that looks like a New Relic API key out of a string."""
    redacted = text
    for pattern in _REDACT_PATTERNS:
        redacted = pattern.sub(lambda m: m.group(1) + "***REDACTED***" if m.lastindex and m.lastindex > 1 else "***REDACTED***", redacted)
    return redacted


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        return redact(message)


def ensure_output_dirs() -> None:
    for d in (LOG_DIR, REPORT_DIR, DATA_DIR, CHANGES_DIR):
        d.mkdir(parents=True, exist_ok=True)


def timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def setup_logger(command_name: str, level: int = logging.INFO) -> logging.Logger:
    """Create a logger that writes to console + outputs/logs/<ts>_<command>.log"""
    ensure_output_dirs()
    logger = logging.getLogger(f"nr_rel.{command_name}")
    logger.setLevel(level)
    logger.handlers.clear()
    logger.propagate = False

    fmt = RedactingFormatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(fmt)
    logger.addHandler(console_handler)

    log_path = LOG_DIR / f"{timestamp()}_{command_name}.log"
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    logger.info("Log file for this run: %s", log_path)
    return logger
