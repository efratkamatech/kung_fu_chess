"""Algebraic square notation: convert between a chess square like ``"e2"`` and a cell.

A square is a file letter (``a``, ``b``, ... -> column 0, 1, ...) plus a rank digit
counted from the *bottom* (rank 1 = bottom row). This is the notation players read and
the wire command uses, so it lives in one shared place: the moves log turns a Position
into a square, and the command parser turns a square back into a Position.

Ranks are a single digit here (boards up to 9 rows), which is all Kung Fu Chess needs.
"""

from __future__ import annotations

from kfchess.model.color import Color
from kfchess.model.position import Position


def build_command(
    color: Color, piece_letter: str, source: Position, target: Position, rows: int
) -> str:
    """Compose a wire move command, e.g. ``build_command(WHITE, "Q", e2, e5) -> "WQe2e5"``.

    The inverse of the server's ``parse_command``: a colour letter (``W``/``B``), the
    piece letter, and the two squares. Used by the client to turn a click into the
    command it sends.
    """
    return (
        f"{color.value.upper()}{piece_letter}"
        f"{position_to_square(source, rows)}{position_to_square(target, rows)}"
    )


def position_to_square(position: Position, rows: int) -> str:
    """The square name for ``position`` on a board ``rows`` high, e.g. ``"e2"``."""
    file = chr(ord("a") + position.col)
    rank = rows - position.row
    return f"{file}{rank}"


def square_to_position(square: str, rows: int) -> Position:
    """The cell a square names on a board ``rows`` high (inverse of the above).

    Raises ``ValueError`` if the square is not a file letter followed by a single rank
    digit. The resulting cell is *not* range-checked here — the caller bounds-checks it
    against the actual board.
    """
    if len(square) != 2:
        raise ValueError(f"malformed square: {square!r}")
    file_char, rank_char = square[0].lower(), square[1]
    if not ("a" <= file_char <= "z"):
        raise ValueError(f"bad file: {square!r}")
    if not rank_char.isdigit():
        raise ValueError(f"bad rank: {square!r}")
    col = ord(file_char) - ord("a")
    row = rows - int(rank_char)
    return Position(row, col)
