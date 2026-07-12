"""Composable movement primitives.

A movement primitive answers one question: can ``piece``, starting at ``source``,
reach ``target`` on this ``board`` using this kind of geometry? New pieces are
built by combining a primitive with *data* (directions, offsets, forward step) —
not by writing new branching logic. That is the design's "pieces are registered,
not coded" rule.

``can_reach`` receives the moving ``piece`` because some geometry depends on it: a
pawn advances by its color and captures only diagonally. Direction-only primitives
(slide, offset) accept the argument and ignore it.

``SlideMovement`` also checks that the path *between* source and target is clear;
the destination cell is left to the RuleEngine (capture vs. blocked-by-friend).
``OffsetMovement`` (the knight) ignores the path — it jumps over blockers.
"""

from __future__ import annotations

from typing import Iterable, Mapping, Optional, Protocol, Tuple

from kfchess.model.board import Board
from kfchess.model.color import Color
from kfchess.model.piece import Piece
from kfchess.model.position import Position

Vector = Tuple[int, int]  # a (d_row, d_col) step or offset


class Movement(Protocol):
    """The common shape of every primitive: decide if a move is reachable."""

    def can_reach(
        self, piece: Piece, source: Position, target: Position, board: Board
    ) -> bool: ...


def _unit(delta: int) -> int:
    """The sign of ``delta``: -1, 0, or +1 (the one-cell step toward the target)."""
    if delta > 0:
        return 1
    if delta < 0:
        return -1
    return 0


class SlideMovement:
    """Move any number of cells (up to ``max_distance``) along fixed directions.

    Rook = the orthogonal directions; bishop = the diagonals; queen = both;
    king = both with ``max_distance=1``. Colour-independent, so ``piece`` is unused.
    """

    def __init__(
        self, directions: Iterable[Vector], max_distance: Optional[int] = None
    ) -> None:
        self._directions = frozenset(directions)
        self._max_distance = max_distance

    def can_reach(
        self, piece: Piece, source: Position, target: Position, board: Board
    ) -> bool:
        d_row = target.row - source.row
        d_col = target.col - source.col
        if d_row == 0 and d_col == 0:
            return False  # a move must go somewhere

        step = (_unit(d_row), _unit(d_col))
        if step not in self._directions:
            return False

        distance = max(abs(d_row), abs(d_col))
        # The delta must be a whole number of unit steps in that direction; this
        # rejects e.g. (2, 1), which points diagonal-ish but is not colinear.
        if (step[0] * distance, step[1] * distance) != (d_row, d_col):
            return False

        if self._max_distance is not None and distance > self._max_distance:
            return False

        # The path must be clear: every cell strictly between source and target
        # (steps 1 .. distance-1) must be empty. The destination is not checked
        # here — landing there may be a capture, which the RuleEngine judges.
        for i in range(1, distance):
            between = source.translated(step[0] * i, step[1] * i)
            if board.piece_at(between) is not None:
                return False
        return True


class OffsetMovement:
    """Jump straight to ``source`` + one of a fixed set of offsets (the knight).

    Colour-independent and path-independent, so ``piece`` and ``board`` are unused.
    """

    def __init__(self, offsets: Iterable[Vector]) -> None:
        self._offsets = frozenset(offsets)

    def can_reach(
        self, piece: Piece, source: Position, target: Position, board: Board
    ) -> bool:
        delta = (target.row - source.row, target.col - source.col)
        return delta in self._offsets


class PawnMovement:
    """Pawn geometry, which depends on the pawn's colour.

    - one step *forward* (by colour) onto an empty cell, or
    - one step *diagonally forward* onto an enemy (a capture), or
    - two steps *forward* from its start row, over a clear path onto an empty cell.

    ``forward_by_color`` gives each colour's forward row step (white = -1 "up",
    black = +1 "down"). Forward capture is not allowed; promotion is handled as an
    arrival effect elsewhere (the arbiter), not here.
    """

    def __init__(self, forward_by_color: Mapping[Color, int]) -> None:
        self._forward = dict(forward_by_color)

    def can_reach(
        self, piece: Piece, source: Position, target: Position, board: Board
    ) -> bool:
        forward = self._forward[piece.color]
        d_row = target.row - source.row
        d_col = target.col - source.col
        occupant = board.piece_at(target)

        if d_row == forward and d_col == 0:
            return occupant is None  # forward: only into an empty cell
        if d_row == forward and abs(d_col) == 1:
            # diagonal: only to capture an enemy piece
            return occupant is not None and occupant.color != piece.color
        if (
            d_row == 2 * forward
            and d_col == 0
            and source.row == self._start_row(forward, board)
        ):
            # double advance from the start row: middle and destination both empty
            middle = source.translated(forward, 0)
            return board.piece_at(middle) is None and occupant is None
        return False

    @staticmethod
    def _start_row(forward: int, board: Board) -> int:
        """The pawn's start row: one step forward from its back rank."""
        back_rank = board.rows - 1 if forward < 0 else 0
        return back_rank + forward
