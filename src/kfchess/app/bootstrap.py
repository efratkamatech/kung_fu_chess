"""Bootstrap: assemble the whole application — the "activation of everything".

This is the single place where subsystems are built and connected. ``main`` just
calls ``build_command_loop()`` and starts it, so ``main`` never changes as the app
grows: each iteration wires its new subsystems here.

There are two levels of wiring:
- once per process: the parser, printer, and the CommandLoop (``build_command_loop``);
- once per fixture: the game state built from that fixture's board — the Clock,
  GameEngine, and Controller (``_build_game``), because the board only exists after
  parsing. The CommandLoop calls this factory for each run.
"""

from __future__ import annotations

from typing import Tuple

from kfchess.app.command_loop import CommandLoop
from kfchess.control.controller import Controller
from kfchess.engine.clock import Clock
from kfchess.engine.game_engine import GameEngine
from kfchess.model.board import Board
from kfchess.model.piece_type import standard_piece_types
from kfchess.text_io.board_parser import BoardParser
from kfchess.text_io.board_printer import BoardPrinter


def build_command_loop() -> CommandLoop:
    """Build the process-level pieces and the CommandLoop that ties them together."""
    parser = BoardParser(standard_piece_types())
    printer = BoardPrinter()
    return CommandLoop(parser, printer, _build_game)


def _build_game(board: Board) -> Tuple[GameEngine, Controller]:
    """Build the per-fixture game state: clock, engine, and controller."""
    clock = Clock()
    engine = GameEngine(board, clock)
    controller = Controller(engine)
    return engine, controller
