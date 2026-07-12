"""RealTimeArbiter: moves take time.

Owns the in-flight motions. Starting a motion records where a piece is going and
when it will arrive (``now + distance * ms_per_cell``); the piece stays on the
board at its origin, marked ``MOVING``, until then. Advancing the clock and calling
``resolve`` applies every motion whose arrival time has passed: the piece is moved
to its destination (capturing whatever settled piece is there) and returns to
``IDLE``.

This is the component that mutates the board when a move completes. It knows the
board, positions, and time, but not chess legality (the RuleEngine judged that
before the motion started), pixels, or the text format.

Distance is the Chebyshev distance (the larger of the row/column deltas) — the
number of cells a sliding piece travels.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from kfchess.model.board import Board
from kfchess.model.piece import Piece, PieceState
from kfchess.model.position import Position


@dataclass(frozen=True)
class Motion:
    """A piece in flight from ``source`` to ``target``, arriving at ``arrival_ms``."""

    piece: Piece
    source: Position
    target: Position
    arrival_ms: int


class RealTimeArbiter:
    """Tracks active motions and applies them to the board as they arrive."""

    def __init__(self, board: Board, ms_per_cell: int) -> None:
        self._board = board
        self._ms_per_cell = ms_per_cell
        self._motions: List[Motion] = []

    def start_motion(
        self, piece: Piece, source: Position, target: Position, now_ms: int
    ) -> None:
        """Begin moving ``piece`` from ``source`` to ``target`` starting at ``now_ms``.

        The piece stays on the board at ``source`` (marked MOVING) until it arrives.
        """
        distance = max(
            abs(target.row - source.row), abs(target.col - source.col)
        )
        arrival_ms = now_ms + distance * self._ms_per_cell
        self._motions.append(Motion(piece, source, target, arrival_ms))
        piece.state = PieceState.MOVING

    def resolve(self, now_ms: int) -> None:
        """Apply every motion that has arrived by ``now_ms``; keep the rest in flight."""
        still_in_flight: List[Motion] = []
        for motion in self._motions:
            if motion.arrival_ms <= now_ms:
                self._board.remove(motion.source)
                self._board.place(motion.target, motion.piece)
                motion.piece.state = PieceState.IDLE
            else:
                still_in_flight.append(motion)
        self._motions = still_in_flight
