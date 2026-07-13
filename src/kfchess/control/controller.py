"""Controller: interpret clicks into selection and move intent.

This is the input layer. It is the only place that knows a click is in *pixels* and
converts it to a board cell, and it holds the "currently selected cell" state. It
reads the board (via the engine) to decide what a click means, and asks the engine
to move when appropriate. It contains no movement rules and no text-format
knowledge.

Click rules (Iteration 2):
- Off the board -> ignored.
- Nothing selected: clicking a piece selects it; clicking an empty cell is ignored.
- Something selected: clicking a *friendly* piece replaces the selection; clicking
  any other cell (empty or enemy) requests a move there and clears the selection.
"""

from __future__ import annotations

from typing import Optional

from kfchess.config import CELL_PX
from kfchess.engine.game_engine import GameEngine
from kfchess.model.position import Position


class Controller:
    """Holds selection state and translates pixel clicks into engine actions."""

    __slots__ = ("_engine", "_selected")

    def __init__(self, engine: GameEngine) -> None:
        self._engine = engine
        self._selected: Optional[Position] = None

    def click(self, x: int, y: int) -> None:
        board = self._engine.board
        position = self._pixel_to_cell(x, y)
        if not board.in_bounds(position):
            return  # clicks outside the board are ignored

        target_piece = board.piece_at(position)

        if self._selected is None:
            # No current selection: only clicking a piece does anything (selects it).
            if target_piece is not None:
                self._selected = position
            return

        # A piece is already selected. While a selection is held the board cannot
        # change under it, so the selected cell always still holds its piece.
        selected_piece = board.piece_at(self._selected)
        clicked_friendly = (
            target_piece is not None
            and target_piece.color == selected_piece.color
        )
        if clicked_friendly:
            self._selected = position  # switch the selection to the new friendly piece
        else:
            self._engine.request_move(self._selected, position)
            self._selected = None

    def jump(self, x: int, y: int) -> None:
        """Make the piece on the clicked cell jump in place (off-board is ignored)."""
        position = self._pixel_to_cell(x, y)
        if self._engine.board.in_bounds(position):
            self._engine.request_jump(position)

    @staticmethod
    def _pixel_to_cell(x: int, y: int) -> Position:
        """Map pixel (x, y) to a board cell: x -> column, y -> row."""
        return Position(y // CELL_PX, x // CELL_PX)
