"""Bootstrap: assemble the whole application — the "activation of everything".

This is the single place where subsystems are built and connected. ``main`` just
calls ``build_command_loop()`` and starts it, so ``main`` never changes as the app
grows: each iteration wires its new subsystems here.

There are two levels of wiring:
- once per process: the parser, printer, and the CommandLoop (``build_command_loop``);
- once per fixture: the game state built from that fixture's board — the Clock,
  GameEngine, and Controller (``build_game``), because the board only exists after
  parsing. The CommandLoop calls this factory for each run. ``build_game`` is public
  so the graphics layer can reuse the exact same wiring for the windowed game.
"""

from __future__ import annotations

from typing import Tuple

from kfchess.app.command_loop import CommandLoop
from kfchess.config import COOLDOWN_MS, JUMP_DURATION_MS, MS_PER_CELL
from kfchess.control.controller import Controller
from kfchess.engine.arbiter import RealTimeArbiter
from kfchess.engine.clock import Clock
from kfchess.engine.game_engine import GameEngine
from kfchess.model.board import Board
from kfchess.model.piece_type import standard_piece_types
from kfchess.movement.rules import PAWN_FORWARD, standard_movement_rules
from kfchess.rules.promotion import Promotion
from kfchess.rules.rule_engine import RuleEngine
from kfchess.text_io.board_parser import BoardParser
from kfchess.text_io.board_printer import BoardPrinter


def build_command_loop() -> CommandLoop:
    """Build the process-level pieces and the CommandLoop that ties them together."""
    parser = BoardParser(standard_piece_types())
    printer = BoardPrinter()
    return CommandLoop(parser, printer, build_game)


def build_game(board: Board) -> Tuple[GameEngine, Controller]:
    """Build the per-fixture game state: clock, rule engine, arbiter, engine, controller."""
    clock = Clock()
    rule_engine = RuleEngine(standard_movement_rules())
    promotion = Promotion(PAWN_FORWARD, standard_piece_types().get("Q"))
    arbiter = RealTimeArbiter(
        board, MS_PER_CELL, promotion, JUMP_DURATION_MS, COOLDOWN_MS
    )
    engine = GameEngine(board, clock, rule_engine, arbiter)
    controller = Controller(engine)
    return engine, controller
