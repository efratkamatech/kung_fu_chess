"""Tests for parse_command: "WQe2e5" -> a validated ParsedMove."""

import pytest

from kfchess.model.color import Color
from kfchess.model.position import Position
from kfchess.server.command_parser import CommandError, parse_command


def test_parses_colour_piece_and_squares():
    move = parse_command("WQe2e5", rows=8, cols=8)
    assert move.color is Color.WHITE
    assert move.piece_letter == "Q"
    assert move.source == Position(6, 4)  # e2 -> row 8-2=6, col e=4
    assert move.target == Position(3, 4)  # e5 -> row 8-5=3, col e=4


def test_a_black_bishop_command_reads_colour_then_piece():
    move = parse_command("BBc8f5", rows=8, cols=8)  # colour B, piece B (bishop)
    assert move.color is Color.BLACK
    assert move.piece_letter == "B"


def test_lowercase_colour_and_piece_are_accepted():
    assert parse_command("wqe2e5", rows=8, cols=8).color is Color.WHITE


@pytest.mark.parametrize(
    "cmd",
    [
        "WQe2e",       # too short
        "WQe2e5x",     # too long
        "XQe2e5",      # bad colour letter
        "WZe2e5",      # bad piece letter
        "WQe9e5",      # rank off the board
        "WQz2e5",      # file off the board
        "WQexe5",      # source rank is not a digit (square_to_position raises)
    ],
)
def test_rejects_a_bad_command(cmd):
    with pytest.raises(CommandError):
        parse_command(cmd, rows=8, cols=8)
