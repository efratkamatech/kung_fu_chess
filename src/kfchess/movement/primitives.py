"""Composable movement primitives.

A movement primitive answers one question: starting from ``source``, can a piece
reach ``target`` on this ``board`` using this kind of geometry? New pieces are
built by combining a primitive with *data* (which directions, which offsets) — not
by writing new branching logic. That is the design's "pieces are registered, not
coded" rule.

``SlideMovement`` also checks that the path *between* source and target is clear
(it cannot slide through a piece); the destination cell itself is left to the
RuleEngine, which knows whether landing there is a capture or blocked by a friend.
``OffsetMovement`` (the knight) ignores the path entirely — it jumps over blockers.
"""

from __future__ import annotations

from typing import Iterable, Optional, Protocol, Tuple

from kfchess.model.board import Board
from kfchess.model.position import Position

Vector = Tuple[int, int]  # a (d_row, d_col) step or offset


class Movement(Protocol):
    """The common shape of every primitive: decide if a move is reachable."""

    def can_reach(self, source: Position, target: Position, board: Board) -> bool: ...


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
    king = both with ``max_distance=1``.
    """

    def __init__(
        self, directions: Iterable[Vector], max_distance: Optional[int] = None
    ) -> None:
        self._directions = frozenset(directions)
        self._max_distance = max_distance

    def can_reach(self, source: Position, target: Position, board: Board) -> bool:
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
        # (i.e. steps 1 .. distance-1) must be empty. The destination itself is not
        # checked here — landing there may be a capture, which the RuleEngine judges.
        for i in range(1, distance):
            between = source.translated(step[0] * i, step[1] * i)
            if board.piece_at(between) is not None:
                return False
        return True


class OffsetMovement:
    """Jump straight to ``source`` + one of a fixed set of offsets (the knight)."""

    def __init__(self, offsets: Iterable[Vector]) -> None:
        self._offsets = frozenset(offsets)

    def can_reach(self, source: Position, target: Position, board: Board) -> bool:
        delta = (target.row - source.row, target.col - source.col)
        return delta in self._offsets
