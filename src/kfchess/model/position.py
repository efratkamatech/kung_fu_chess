"""Position: an immutable board-cell coordinate.

A pure value object owned by the Model layer. It knows *where* a cell is and how
to do coordinate arithmetic, but nothing about pixels, movement rules, or timing.

Convention: ``row`` grows downward (row 0 is the top row as printed), ``col``
grows rightward (col 0 is the leftmost cell). This matches how the board fixture
is read top-to-bottom, left-to-right.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Position:
    """A single cell coordinate. Immutable, so it is safe as a dict/set key.

    ``slots=True`` keeps each instance lean (no per-object ``__dict__``), which
    matters because positions are created in large numbers during move checks.
    """

    row: int
    col: int

    def translated(self, d_row: int, d_col: int) -> "Position":
        """Return a new Position offset by (``d_row``, ``d_col``).

        Pure arithmetic — it does not check board bounds; callers that care about
        the board edge (the Board / movement layers) validate the result.
        """
        return Position(self.row + d_row, self.col + d_col)
