"""Tests for algebraic square notation (position <-> square)."""

import pytest

from kfchess.algebraic import build_command, position_to_square, square_to_position
from kfchess.model.color import Color
from kfchess.model.position import Position


def test_build_command_composes_colour_piece_and_squares():
    cmd = build_command(Color.WHITE, "Q", Position(6, 4), Position(3, 4), rows=8)
    assert cmd == "WQe2e5"
    assert build_command(Color.BLACK, "N", Position(0, 1), Position(2, 2), rows=8) == "BNb8c6"


def test_position_to_square_reads_file_and_rank_from_the_bottom():
    assert position_to_square(Position(7, 0), rows=8) == "a1"  # bottom-left
    assert position_to_square(Position(0, 4), rows=8) == "e8"  # top, e-file


def test_square_to_position_is_the_inverse():
    for row in range(8):
        for col in range(8):
            square = position_to_square(Position(row, col), rows=8)
            assert square_to_position(square, rows=8) == Position(row, col)


def test_square_to_position_accepts_an_uppercase_file():
    assert square_to_position("E2", rows=8) == square_to_position("e2", rows=8)


@pytest.mark.parametrize("bad", ["e", "e22", "12", "e!", ""])
def test_square_to_position_rejects_a_malformed_square(bad):
    with pytest.raises(ValueError):
        square_to_position(bad, rows=8)
