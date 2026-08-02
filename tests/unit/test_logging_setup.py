"""Tests for configure_logging: where the logs go, and what shape they arrive in.

The two things worth holding to. A container's log is its standard output, so writing
only to a file means `docker compose logs` shows an empty screen — which is what it did
for four stages. And a field attached at a call site has to survive into *both* formats,
or adding one would improve the searchable log by quietly removing something from the
readable one.
"""

import json
import logging

from kfchess.logging_setup import configure_logging


def _close(logger):
    """Release the file handler(s) so the temp file can be cleaned up on Windows."""
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)


def logged(tmp_path, name, message, json_format=False, **fields):
    """Log one line and hand back what landed in the file."""
    path = tmp_path / "activity.log"
    logger = configure_logging(name, path, json_format=json_format)
    try:
        logger.info(message, extra=fields)
    finally:
        _close(logger)
    return path.read_text(encoding="utf-8").strip()


def test_configured_logger_writes_info_lines_to_the_file(tmp_path):
    assert "hello world" in logged(tmp_path, "kfchess.test.write", "hello world")


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
        assert len(logger.handlers) == 2  # one file, one stream -- not four
    finally:
        _close(logger)


def test_logs_go_to_standard_output_as_well_as_the_file(tmp_path, capsys):
    """The gap open since S1: in a container, the file is nobody's log."""
    logger = configure_logging("kfchess.test.stream", tmp_path / "activity.log")
    try:
        logger.info("visible in docker compose logs")
    finally:
        _close(logger)

    assert "visible in docker compose logs" in capsys.readouterr().out


# --- the two formats -----------------------------------------------------------

def test_the_readable_format_is_a_line_a_person_can_read(tmp_path):
    line = logged(tmp_path, "kfchess.test.readable", "client 3 seated")

    assert line.endswith("INFO kfchess.test.readable: client 3 seated")


def test_the_structured_format_is_one_json_object(tmp_path):
    entry = json.loads(logged(tmp_path, "kfchess.test.json", "seated", json_format=True))

    assert entry["message"] == "seated"
    assert entry["level"] == "INFO"
    assert entry["logger"] == "kfchess.test.json"
    assert "time" in entry


def test_fields_attached_at_the_call_site_become_json_fields(tmp_path):
    """What makes ten containers searchable: a field, not a regular expression."""
    entry = json.loads(
        logged(
            tmp_path, "kfchess.test.fields", "seated",
            json_format=True, room_id="7C2FQK", shard_id="sh1", user_id="Efrat",
        )
    )

    assert entry["room_id"] == "7C2FQK"
    assert entry["shard_id"] == "sh1"
    assert entry["user_id"] == "Efrat"


def test_the_json_carries_nothing_logging_added_by_itself(tmp_path):
    """Two dozen internal attributes ride on every record. None of them is a field."""
    entry = json.loads(logged(tmp_path, "kfchess.test.clean", "hello", json_format=True))

    assert set(entry) == {"time", "level", "logger", "message"}


def test_the_same_fields_are_appended_to_the_readable_line(tmp_path):
    """Adding a field must not improve one format by emptying the other."""
    line = logged(tmp_path, "kfchess.test.both", "seated", room_id="7C2FQK")

    assert line.endswith("seated room_id=7C2FQK")


def test_a_traceback_is_carried_as_a_field_rather_than_as_extra_lines(tmp_path):
    """A stack trace split over forty lines is forty log entries to anything indexing it."""
    path = tmp_path / "activity.log"
    logger = configure_logging("kfchess.test.error", path, json_format=True)
    try:
        try:
            raise ValueError("no free room id")
        except ValueError:
            logger.exception("could not open a room")
    finally:
        _close(logger)

    entry = json.loads(path.read_text(encoding="utf-8").strip())
    assert "ValueError: no free room id" in entry["error"]
