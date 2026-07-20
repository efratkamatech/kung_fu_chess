"""Parse a wire move command like ``"WQe2e5"`` into a validated :class:`ParsedMove`.

The command is six characters: a colour letter (``W``/``B``), a piece letter
(``K``/``Q``/``R``/``B``/``N``/``P``), a from-square, and a to-square — e.g. ``WQe2e5``
is "white queen, e2 to e5". Parsing is *pure*: it checks the format and that both
squares fall on the board, and it produces the colour, piece letter, and cells. It does
**not** check that the source actually holds that piece or that it belongs to the
requesting player — those need the live board, and the GameSession does them.
"""

from __future__ import annotations

from dataclasses import dataclass

from kfchess.algebraic import square_to_position
from kfchess.model.color import Color
from kfchess.model.position import Position

_COLOR_BY_LETTER = {"W": Color.WHITE, "B": Color.BLACK}
_PIECE_LETTERS = frozenset("KQRBNP")
_COMMAND_LENGTH = 6


class CommandError(ValueError):
    """A move command that cannot be parsed or names a square off the board."""


@dataclass(frozen=True)
class ParsedMove:
    """The pieces of a parsed command: who moves what, from where, to where."""

    color: Color
    piece_letter: str
    source: Position
    target: Position


def parse_command(cmd: str, rows: int, cols: int) -> ParsedMove:
    """Parse ``cmd`` against a ``rows`` x ``cols`` board, or raise :class:`CommandError`."""
    if len(cmd) != _COMMAND_LENGTH:
        raise CommandError(f"expected {_COMMAND_LENGTH} characters: {cmd!r}")
    color_letter, piece_letter = cmd[0].upper(), cmd[1].upper()
    if color_letter not in _COLOR_BY_LETTER:
        raise CommandError(f"unknown colour letter: {cmd[0]!r}")
    if piece_letter not in _PIECE_LETTERS:
        raise CommandError(f"unknown piece letter: {cmd[1]!r}")
    try:
        source = square_to_position(cmd[2:4], rows)
        target = square_to_position(cmd[4:6], rows)
    except ValueError as error:
        raise CommandError(str(error)) from error
    for cell in (source, target):
        if not (0 <= cell.row < rows and 0 <= cell.col < cols):
            raise CommandError(f"square off the board: {cell}")
    return ParsedMove(_COLOR_BY_LETTER[color_letter], piece_letter, source, target)
