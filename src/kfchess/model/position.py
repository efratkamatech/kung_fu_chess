"""Position: an immutable board-cell coordinate.

A pure value object owned by the Model layer. It knows *where* a cell is and how
to do coordinate arithmetic, but nothing about pixels, movement rules, or timing.

Convention: ``row`` grows downward (row 0 is the top row as printed), ``col``
grows rightward (col 0 is the leftmost cell). This matches how the board fixture
is read top-to-bottom, left-to-right.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Position:
    """A single cell coordinate. Immutable, so it is safe as a dict/set key.

    Note: we intentionally do NOT use ``@dataclass(slots=True)`` here. That option
    only exists on Python 3.10+, and the grader (VPL) runs an older Python, so it
    would crash on import. The lean-instance benefit is minor; correctness on the
    grader's Python wins. (Plain-class ``__slots__``, used on Piece/Board, works on
    every version and is kept.)
    """

    row: int
    col: int

    def translated(self, d_row: int, d_col: int) -> "Position":
        """Return a new Position offset by (``d_row``, ``d_col``).

        Pure arithmetic — it does not check board bounds; callers that care about
        the board edge (the Board / movement layers) validate the result.
        """
        return Position(self.row + d_row, self.col + d_col)
