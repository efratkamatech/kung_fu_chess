from kfchess.app.command_loop import CommandLoop
from kfchess.config import (
    ERR_MISSING_BOARD_SECTION,
    ERR_UNKNOWN_COMMAND,
    error_message,
)
from kfchess.model.piece_type import standard_piece_types
from kfchess.text_io.board_parser import BoardParser
from kfchess.text_io.board_printer import BoardPrinter


def make_loop():
    return CommandLoop(BoardParser(standard_piece_types()), BoardPrinter())


def test_print_board_renders_grid():
    assert make_loop().run("Board:\nwK bK\nCommands:\nprint board\n") == "wK bK"


def test_unknown_command_yields_error_line():
    out = make_loop().run("Board:\nwK bK\nCommands:\nfoo\n")
    assert out == error_message(ERR_UNKNOWN_COMMAND)


def test_malformed_fixture_returns_error_line():
    out = make_loop().run("Commands:\nprint board\n")
    assert out == error_message(ERR_MISSING_BOARD_SECTION)


def test_multiple_commands_joined_by_newline():
    out = make_loop().run("Board:\nwK bK\nCommands:\nprint board\nfoo\n")
    assert out == "wK bK\n" + error_message(ERR_UNKNOWN_COMMAND)
