from kfchess.app.command_loop import CommandLoop
from kfchess.config import (
    ERR_MISSING_BOARD_SECTION,
    ERR_UNKNOWN_COMMAND,
    error_message,
)
from kfchess.config import MS_PER_CELL
from kfchess.control.controller import Controller
from kfchess.engine.arbiter import RealTimeArbiter
from kfchess.engine.clock import Clock
from kfchess.engine.game_engine import GameEngine
from kfchess.model.piece_type import standard_piece_types
from kfchess.movement.rules import standard_movement_rules
from kfchess.rules.rule_engine import RuleEngine
from kfchess.text_io.board_parser import BoardParser
from kfchess.text_io.board_printer import BoardPrinter


def _build_game(board):
    engine = GameEngine(
        board,
        Clock(),
        RuleEngine(standard_movement_rules()),
        RealTimeArbiter(board, MS_PER_CELL),
    )
    return engine, Controller(engine)


def make_loop():
    return CommandLoop(
        BoardParser(standard_piece_types()), BoardPrinter(), _build_game
    )


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


def test_click_move_wait_then_print():
    text = (
        "Board:\nwK . .\n. . .\n. . .\n"
        "Commands:\nclick 50 50\nclick 150 150\nwait 1000\nprint board\n"
    )
    assert make_loop().run(text) == ". . .\n. wK .\n. . ."


def test_click_and_wait_alone_produce_no_output():
    out = make_loop().run("Board:\nwK .\n. .\nCommands:\nclick 50 50\nwait 500\n")
    assert out == ""
