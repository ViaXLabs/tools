import logging
from typing import Optional


def setup_logging(log_file: Optional[str] = None, verbose: bool = False) -> logging.Logger:
    """
    Logging helper:
      - always logs to console
      - optional --log-file writes detailed logs to a file
      - --verbose shows more detail on console
    """
    logger = logging.getLogger("nr_tag_tool")
    logger.setLevel(logging.DEBUG)

    # Avoid duplicate handlers in repeated runs/imports
    if logger.handlers:
        return logger

    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG if verbose else logging.INFO)
    console.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    logger.addHandler(console)

    if log_file:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(fh)

    return logger
