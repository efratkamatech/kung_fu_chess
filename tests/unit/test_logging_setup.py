"""Tests for configure_logging: a named logger writes to a file, replacing handlers."""

import logging

from kfchess.logging_setup import configure_logging


def _close(logger):
    """Release the file handler(s) so the temp file can be cleaned up on Windows."""
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)


def test_configured_logger_writes_info_lines_to_the_file(tmp_path):
    path = tmp_path / "activity.log"
    logger = configure_logging("kfchess.test.write", path)
    try:
        logger.info("hello %s", "world")
    finally:
        _close(logger)
    assert "hello world" in path.read_text(encoding="utf-8")


def test_a_child_logger_propagates_to_the_configured_parent(tmp_path):
    path = tmp_path / "activity.log"
    parent = configure_logging("kfchess.test.parent", path)
    try:
        logging.getLogger("kfchess.test.parent.child").info("from the child")
    finally:
        _close(parent)
    assert "from the child" in path.read_text(encoding="utf-8")


def test_configuring_twice_does_not_duplicate_handlers(tmp_path):
    name = "kfchess.test.twice"
    configure_logging(name, tmp_path / "one.log")
    logger = configure_logging(name, tmp_path / "two.log")
    try:
        assert len(logger.handlers) == 1  # the first handler was replaced, not stacked
    finally:
        _close(logger)
