"""CommandLoop: run a fixture's commands and produce the output text.

Part of the app layer. It receives its collaborators (parser, printer, and a
game-factory) already built, and just *runs* commands. Per fixture it asks the
factory to build the game state (engine + controller) from the parsed board, then
dispatches each command:

- ``print board`` -> render the current board (produces output);
- ``click x y``   -> Controller interprets the click (no output);
- ``wait ms``     -> GameEngine advances the clock (no output);
- anything else   -> ``ERROR UNKNOWN_COMMAND`` (produces output).

Commands that only change state return no line, so ``_execute`` returns
``Optional[str]`` and only real output is collected.
"""

from __future__ import annotations

from typing import Callable, Optional, Tuple

from kfchess.config import (
    CMD_CLICK,
    CMD_JUMP,
    CMD_PRINT_BOARD,
    CMD_WAIT,
    ERR_UNKNOWN_COMMAND,
    error_message,
)
from kfchess.control.controller import Controller
from kfchess.engine.game_engine import GameEngine
from kfchess.model.board import Board
from kfchess.text_io.board_parser import BoardParser, FixtureError
from kfchess.text_io.board_printer import BoardPrinter

# A game-factory turns a parsed board into the per-fixture (engine, controller).
GameFactory = Callable[[Board], Tuple[GameEngine, Controller]]


class CommandLoop:
    """Executes the commands from a parsed fixture, returning the combined output."""

    def __init__(
        self,
        parser: BoardParser,
        printer: BoardPrinter,
        game_factory: GameFactory,
    ) -> None:
        self._parser = parser
        self._printer = printer
        self._game_factory = game_factory

    def run(self, text: str) -> str:
        try:
            fixture = self._parser.parse(text)
        except FixtureError as error:
            return error_message(error.code)

        engine, controller = self._game_factory(fixture.board)
        outputs = []
        for command in fixture.commands:
            output = self._execute(command, engine, controller)
            if output is not None:
                outputs.append(output)
        return "\n".join(outputs)

    def _execute(
        self, command: str, engine: GameEngine, controller: Controller
    ) -> Optional[str]:
        """Run one command; return its output line, or None if it produces none."""
        if command == CMD_PRINT_BOARD:
            return self._printer.render(engine.board)

        parts = command.split()
        verb = parts[0]
        if verb == CMD_CLICK:
            controller.click(int(parts[1]), int(parts[2]))
            return None
        if verb == CMD_JUMP:
            controller.jump(int(parts[1]), int(parts[2]))
            return None
        if verb == CMD_WAIT:
            engine.wait(int(parts[1]))
            return None
        return error_message(ERR_UNKNOWN_COMMAND)
