import logging
from typing import Optional


def setup_logging(log_file: Optional[str] = None, verbose: bool = False) -> logging.Logger:
    """
    Simple logging:
      - console always
      - optional file via --log-file
      - --verbose increases console detail
    """
    logger = logging.getLogger("nr_tag_tool")
    logger.setLevel(logging.DEBUG)

    # Prevent duplicate handlers if re-imported
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
