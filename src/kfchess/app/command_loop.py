"""CommandLoop: run a fixture's commands and produce the output text.

Part of the app layer. It receives its collaborators (parser, printer) already
built and just *runs* commands one at a time — it never constructs anything, since
assembly is the bootstrap's job. Keeping "running" separate from "wiring" makes
this class easy to test with injected fakes.

Iteration 1 recognizes only ``print board``; any other command yields
``UNKNOWN_COMMAND`` and processing continues. Iteration 2 extends ``_execute`` with
``click`` and ``wait`` (delegating to the Controller and GameEngine).
"""

from __future__ import annotations

from kfchess.config import CMD_PRINT_BOARD, ERR_UNKNOWN_COMMAND, error_message
from kfchess.model.board import Board
from kfchess.text_io.board_parser import BoardParser, FixtureError
from kfchess.text_io.board_printer import BoardPrinter


class CommandLoop:
    """Executes the commands from a parsed fixture, returning the combined output."""

    def __init__(self, parser: BoardParser, printer: BoardPrinter) -> None:
        self._parser = parser
        self._printer = printer

    def run(self, text: str) -> str:
        """Parse the fixture and run its commands; return everything to print.

        A malformed fixture yields just its error code (parsing raises before any
        command runs).
        """
        try:
            fixture = self._parser.parse(text)
        except FixtureError as error:
            return error_message(error.code)

        outputs = [self._execute(command, fixture.board) for command in fixture.commands]
        return "\n".join(outputs)

    def _execute(self, command: str, board: Board) -> str:
        """Run a single command and return its output line(s)."""
        if command == CMD_PRINT_BOARD:
            return self._printer.render(board)
        return error_message(ERR_UNKNOWN_COMMAND)
