import pytest

from kfchess.config import (
    ERR_INVALID_PIECE,
    ERR_MISSING_BOARD_SECTION,
    ERR_MISSING_COMMANDS_SECTION,
)
from kfchess.model.piece_type import standard_piece_types
from kfchess.model.position import Position
from kfchess.text_io.board_parser import BoardParser, FixtureError, ParsedFixture


def make_parser():
    return BoardParser(standard_piece_types())


def test_parses_board_and_commands():
    text = "Board:\nwK . bK\n. . .\nCommands:\nprint board\n"
    fixture = make_parser().parse(text)
    assert isinstance(fixture, ParsedFixture)
    assert fixture.board.rows == 2
    assert fixture.board.cols == 3
    assert fixture.commands == ["print board"]
    assert fixture.board.piece_at(Position(0, 0)).piece_type.letter == "K"
    assert fixture.board.piece_at(Position(0, 0)).color.prefix == "w"
    assert fixture.board.is_empty(Position(0, 1))


def test_missing_board_section():
    with pytest.raises(FixtureError) as exc:
        make_parser().parse("Commands:\nprint board\n")
    assert exc.value.code == ERR_MISSING_BOARD_SECTION


def test_missing_commands_section():
    with pytest.raises(FixtureError) as exc:
        make_parser().parse("Board:\nwK bK\n")
    assert exc.value.code == ERR_MISSING_COMMANDS_SECTION


def test_unknown_piece_letter_is_invalid_piece():
    with pytest.raises(FixtureError) as exc:
        make_parser().parse("Board:\nwZ\nCommands:\nprint board\n")
    assert exc.value.code == ERR_INVALID_PIECE


def test_bad_color_prefix_is_invalid_piece():
    with pytest.raises(FixtureError) as exc:
        make_parser().parse("Board:\nxK\nCommands:\nprint board\n")
    assert exc.value.code == ERR_INVALID_PIECE


def test_blank_lines_skipped_and_commands_trimmed():
    text = "Board:\nwK bK\n\nCommands:\n  print board  \n\n"
    fixture = make_parser().parse(text)
    assert fixture.board.rows == 1
    assert fixture.commands == ["print board"]
