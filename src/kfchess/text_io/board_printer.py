"""BoardPrinter: render a Board as canonical text.

The other half of the Text I/O layer. It walks the board through the Board's
public query API and assembles each cell's text token here — an empty cell is the
empty-cell marker, a piece is its color prefix followed by its type letter (``wK``).
Assembling the token is a text-format concern, so it lives here rather than on the
Piece, keeping the model free of formatting knowledge.

Canonical form (per the confirmed spec): the grid only — space-separated cells per
row, rows separated by newlines, and no ``Board:`` header. The trailing newline is
added by the caller when it prints the result.
"""

from __future__ import annotations

from typing import Optional

from kfchess.config import CELL_SEPARATOR, EMPTY_CELL
from kfchess.model.board import Board
from kfchess.model.piece import Piece
from kfchess.model.position import Position


class BoardPrinter:
    """Renders a Board to its canonical multi-line string form."""

    def render(self, board: Board) -> str:
        rows = [self._render_row(board, row) for row in range(board.rows)]
        return "\n".join(rows)

    def _render_row(self, board: Board, row: int) -> str:
        cells = [
            self._render_cell(board.piece_at(Position(row, col)))
            for col in range(board.cols)
        ]
        return CELL_SEPARATOR.join(cells)

    @staticmethod
    def _render_cell(piece: Optional[Piece]) -> str:
        if piece is None:
            return EMPTY_CELL
        return f"{piece.color.prefix}{piece.piece_type.letter}"
