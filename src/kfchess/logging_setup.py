"""Central logging setup: point one named logger at a file, in one place.

Both sides log through the standard :mod:`logging` module — the server under the
``kfchess.server`` tree and the client under ``kfchess.client`` — using module-level
loggers (``logging.getLogger(__name__)``). Those loggers stay unconfigured (and so
silent) under tests; the entry points call :func:`configure_logging` once to attach a
file so every child logger's records land in ``server.log`` / ``client.log``.

Keeping the format and file wiring here means a module never has to know *where* it
logs — it just logs — exactly the config-not-constants rule the rest of the code follows.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Union

_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configure_logging(name: str, path: Union[str, Path]) -> logging.Logger:
    """Send the ``name`` logger (and its children) to ``path`` at INFO and above.

    Replaces any handlers already on the logger, so calling it twice does not double
    every line. Returns the configured logger for the caller to hold if it wishes.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    for existing in list(logger.handlers):
        logger.removeHandler(existing)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter(_FORMAT))
    logger.addHandler(handler)
    return logger
