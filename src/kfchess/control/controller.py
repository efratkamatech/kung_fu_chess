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

Stale selections: this is real-time chess, so between the two clicks of a
select-then-move the board can change under the selection. An enemy can capture the
selected piece and stand on its cell, or the piece can finish an in-flight move and
leave. A held selection therefore records *which* piece was selected (not just the
cell) and, on the next click, checks that the exact piece is still on that cell. If
it is gone, the selection is dropped and the click is treated as a fresh first click
(rather than moving whatever now sits on the old cell, or crashing on an empty one).
"""

from __future__ import annotations

from typing import Optional

from kfchess.config import CELL_PX
from kfchess.engine.game_engine import GameEngine
from kfchess.model.piece import Piece
from kfchess.model.position import Position


class Controller:
    """Holds selection state and translates pixel clicks into engine actions."""

    __slots__ = ("_engine", "_selected", "_selected_piece")

    def __init__(self, engine: GameEngine) -> None:
        self._engine = engine
        self._selected: Optional[Position] = None
        self._selected_piece: Optional[Piece] = None

    @property
    def selected_cell(self) -> Optional[Position]:
        """The currently selected cell, or ``None`` — read by the renderer to highlight it."""
        return self._selected

    def click(self, x: int, y: int) -> None:
        board = self._engine.board
        position = self._pixel_to_cell(x, y)
        if not board.in_bounds(position):
            return

        target_piece = board.piece_at(position)

        # Drop a stale selection: if the exact piece we selected is no longer sitting
        # on the selected cell (captured and replaced, or moved away leaving it
        # empty), forget it so this click is interpreted fresh below.
        if (
            self._selected is not None
            and board.piece_at(self._selected) is not self._selected_piece
        ):
            self._clear_selection()

        if self._selected is None:
            # No live selection: only clicking a piece does anything (selects it).
            if target_piece is not None:
                self._select(position, target_piece)
            return

        # A live selection is held, and its piece is still on the selected cell.
        clicked_friendly = (
            target_piece is not None
            and target_piece.color == self._selected_piece.color
        )
        if clicked_friendly:
            self._select(position, target_piece)  # switch to the new friendly piece
        else:
            self._engine.request_move(self._selected, position)
            self._clear_selection()

    def _select(self, position: Position, piece: Piece) -> None:
        """Record ``piece`` at ``position`` as the current selection."""
        self._selected = position
        self._selected_piece = piece

    def _clear_selection(self) -> None:
        """Forget the current selection (both the cell and the piece)."""
        self._selected = None
        self._selected_piece = None

    def deselect(self) -> None:
        """Public: drop the current selection (used by the GUI after a jump)."""
        self._clear_selection()

    def cell_at(self, x: int, y: int) -> Position:
        """Public: the board cell a pixel maps to (so callers don't repeat the math)."""
        return self._pixel_to_cell(x, y)

    def jump(self, x: int, y: int) -> None:
        """Make the piece on the clicked cell jump in place (off-board is ignored)."""
        position = self._pixel_to_cell(x, y)
        if self._engine.board.in_bounds(position):
            self._engine.request_jump(position)

    @staticmethod
    def _pixel_to_cell(x: int, y: int) -> Position:
        """Map pixel (x, y) to a board cell: x -> column, y -> row."""
        return Position(y // CELL_PX, x // CELL_PX)
