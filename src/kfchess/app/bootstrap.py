"""Bootstrap: assemble the whole application — the "activation of everything".

This is the single place where every subsystem is built and connected. ``main``
just calls ``build_command_loop()`` and starts it, so ``main`` never changes as the
app grows: later iterations construct and wire their new subsystems *here*
(GameEngine, RealTimeArbiter, Clock, Controller, ...), then hand them to the
CommandLoop.

Keeping assembly in one function is dependency injection in practice — each piece
receives what it needs from this builder instead of constructing its own, which is
what makes every layer testable in isolation.
"""

from __future__ import annotations

from kfchess.app.command_loop import CommandLoop
from kfchess.model.piece_type import standard_piece_types
from kfchess.text_io.board_parser import BoardParser
from kfchess.text_io.board_printer import BoardPrinter


def build_command_loop() -> CommandLoop:
    """Build and connect every subsystem, returning the ready-to-run CommandLoop."""
    parser = BoardParser(standard_piece_types())
    printer = BoardPrinter()
    return CommandLoop(parser, printer)
