import logging as std_logging
import sys


def setup_logging() -> std_logging.Logger:
    """Initialize and return the shared application logger."""
    logger = std_logging.getLogger("LottoGen")
    if logger.handlers:
        return logger

    logger.setLevel(std_logging.DEBUG)
    logger.propagate = False

    formatter = std_logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = std_logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


logger = setup_logging()


__all__ = ["logger", "setup_logging"]
