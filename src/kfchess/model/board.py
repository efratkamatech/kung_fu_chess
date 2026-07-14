"""Board: the encapsulated container of pieces on a grid.

Only the Board knows how pieces are stored internally (currently a dict keyed by
Position). Every other layer uses the public methods below, so the storage layout
can be swapped later — e.g. a binary/array representation — without touching any
other code. That is one of the design's explicit future-proofing constraints.

The Board owns *positions*: it is the single source of truth for where each piece
sits. It knows nothing about movement rules, timing, pixels, or the text format.
"""

from __future__ import annotations

from typing import Optional, Sequence

from kfchess.model.piece import Piece
from kfchess.model.position import Position


class Board:
    """A rectangular grid of cells, each empty or holding one Piece."""

    __slots__ = ("_rows", "_cols", "_pieces")

    def __init__(self, rows: int, cols: int) -> None:
        if rows <= 0 or cols <= 0:
            raise ValueError(
                f"board dimensions must be positive, got {rows}x{cols}"
            )
        self._rows = rows
        self._cols = cols
        # Internal storage — private and swappable. Only occupied cells are kept;
        # an absent key means an empty cell.
        self._pieces: dict[Position, Piece] = {}

    # --- dimensions ----------------------------------------------------------
    @property
    def rows(self) -> int:
        return self._rows

    @property
    def cols(self) -> int:
        return self._cols

    # --- queries -------------------------------------------------------------
    def in_bounds(self, position: Position) -> bool:
        """True if ``position`` lies on the board."""
        return 0 <= position.row < self._rows and 0 <= position.col < self._cols

    def piece_at(self, position: Position) -> Optional[Piece]:
        """The piece at ``position``, or ``None`` if the cell is empty.

        Raises ``IndexError`` if ``position`` is off the board — callers that may
        reference off-board cells (e.g. click handling) check ``in_bounds`` first.
        """
        self._require_in_bounds(position)
        return self._pieces.get(position)

    def is_empty(self, position: Position) -> bool:
        """True if the cell at ``position`` holds no piece."""
        return self.piece_at(position) is None

    # --- mutation ------------------------------------------------------------
    def place(self, position: Position, piece: Piece) -> None:
        """Put ``piece`` on the cell at ``position`` (overwriting any occupant)."""
        self._require_in_bounds(position)
        self._pieces[position] = piece

    def remove(self, position: Position) -> Optional[Piece]:
        """Clear the cell at ``position``, returning the piece that was there (or None)."""
        self._require_in_bounds(position)
        return self._pieces.pop(position, None)

    # --- construction --------------------------------------------------------
    @classmethod
    def from_grid(cls, grid: Sequence[Sequence[Optional[Piece]]]) -> "Board":
        """Build a Board from a rectangular grid of cells (``None`` = empty).

        Dimensions are *inferred* from the grid: rows from the number of grid
        rows, cols from the row width. Raises ``ValueError`` on an empty or ragged
        (non-rectangular) grid.
        """
        rows = len(grid)
        if rows == 0:
            raise ValueError("board must have at least one row")
        cols = len(grid[0])
        for r, row in enumerate(grid):
            if len(row) != cols:
                raise ValueError(
                    f"ragged board: row {r} has {len(row)} cells, expected {cols}"
                )
        board = cls(rows, cols)
        for r, row in enumerate(grid):
            for c, piece in enumerate(row):
                if piece is not None:
                    board.place(Position(r, c), piece)
        return board

    # --- internal helpers ----------------------------------------------------
    def _require_in_bounds(self, position: Position) -> None:
        if not self.in_bounds(position):
            raise IndexError(f"position out of bounds: {position!r}")
