"""Central logging setup: where a named logger writes, and in what shape, in one place.

Both sides log through the standard :mod:`logging` module — the server under the
``kfchess.server`` tree and the client under ``kfchess.client`` — using module-level
loggers (``logging.getLogger(__name__)``). Those loggers stay unconfigured (and so
silent) under tests; the entry points call :func:`configure_logging` once.

**Two handlers, not one, and that was a bug for four stages.** A container's log is its
standard output; a process that writes only to a file inside itself has, as far as
``docker compose logs`` is concerned, nothing to say. The file stays — it is what a
laptop run wants, and it survives the process — and the stream is added beside it.

**Two formats, and which one is right depends on who is reading.** A person tailing a log
on one machine wants a line they can read. Ten shards and three gateways being searched
at once want fields: which shard, which room, which player, as JSON that a log system can
index instead of a regular expression somebody has to maintain. So the format follows the
deployment — :data:`~kfchess.config.LOG_JSON` — and the fields ride on the record itself::

    _log.info("seated", extra={"room_id": room, "user_id": name})

Anything passed that way is a field in the JSON and is appended to the readable line, so
one call site serves both formats and neither has a string built for it by hand.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Union

from kfchess.config import LOG_JSON

_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

# What every LogRecord carries whether anybody asked for it or not. Anything *not* in
# here was put there by a call site, which is exactly what makes it worth publishing.
_BUILT_IN = frozenset(
    logging.LogRecord("", 0, "", 0, "", None, None).__dict__
) | {"asctime", "message", "taskName"}


class StructuredFormatter(logging.Formatter):
    """One JSON object per line, with whatever the call site attached to the record."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "time": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        entry.update(_extras(record))
        if record.exc_info:
            entry["error"] = self.formatException(record.exc_info)
        return json.dumps(entry)


class ReadableFormatter(logging.Formatter):
    """The old human line, with any structured fields tacked on the end.

    So that adding a field to a call site improves the searchable format without
    quietly removing anything from the one a person is watching scroll past.
    """

    def __init__(self) -> None:
        super().__init__(_FORMAT)

    def format(self, record: logging.LogRecord) -> str:
        line = super().format(record)
        extras = _extras(record)
        if not extras:
            return line
        return line + " " + " ".join(f"{key}={value}" for key, value in extras.items())


def configure_logging(
    name: str, path: Union[str, Path], json_format: bool = None
) -> logging.Logger:
    """Send the ``name`` logger (and its children) to ``path`` *and* to stdout, at INFO.

    Replaces any handlers already on the logger, so calling it twice does not double
    every line. Returns the configured logger for the caller to hold if it wishes.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    for existing in list(logger.handlers):
        logger.removeHandler(existing)
    formatter = (
        StructuredFormatter()
        if (LOG_JSON if json_format is None else json_format)
        else ReadableFormatter()
    )
    for handler in (logging.FileHandler(path, encoding="utf-8"),
                    logging.StreamHandler(sys.stdout)):
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger


def _extras(record: logging.LogRecord) -> dict:
    """Only what a call site attached — never the two dozen fields logging adds itself."""
    return {
        key: value
        for key, value in record.__dict__.items()
        if key not in _BUILT_IN and not key.startswith("_")
    }
