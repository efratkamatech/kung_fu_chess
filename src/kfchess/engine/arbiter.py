"""RealTimeArbiter: moves take time, and crossing pieces collide.

Owns the in-flight motions. Starting a motion records where a piece is going, when
it started, and when it will arrive (``now + distance * ms_per_cell``); the piece
stays on the board at its origin, marked ``MOVING``, until then.

``resolve`` applies every motion that has arrived, in **start order** (earlier
start time first; command order breaks ties). Applying a motion moves the piece to
its destination and captures whatever piece is there. Because a moving piece stays
at its origin until it arrives, two enemies crossing toward each other's squares
are resolved by this rule automatically: the one that started first lands on the
other (still sitting at its origin) and captures it — and the captured piece's own
motion is cancelled so it cannot also complete.

The arbiter knows the board, positions, and time, but not chess legality (judged by
the RuleEngine before a motion starts), pixels, or the text format.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Set

from kfchess.model.board import Board
from kfchess.model.piece import Piece, PieceState
from kfchess.model.position import Position


@dataclass(frozen=True)
class Motion:
    """A piece in flight, with its timing and a sequence number for ordering."""

    piece: Piece
    source: Position
    target: Position
    start_ms: int
    arrival_ms: int
    sequence: int  # order the motion was started (tie-breaker for "started first")


class RealTimeArbiter:
    """Tracks active motions and applies them — resolving collisions by start order."""

    def __init__(self, board: Board, ms_per_cell: int) -> None:
        self._board = board
        self._ms_per_cell = ms_per_cell
        self._motions: List[Motion] = []
        self._next_sequence = 0
        self._game_over = False

    @property
    def is_game_over(self) -> bool:
        """True once a king has been captured (the game has ended)."""
        return self._game_over

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
        self._motions.append(
            Motion(piece, source, target, now_ms, arrival_ms, self._next_sequence)
        )
        self._next_sequence += 1
        piece.state = PieceState.MOVING

    def resolve(self, now_ms: int) -> None:
        """Apply every motion that has arrived by ``now_ms``, in start order."""
        arrived = [m for m in self._motions if m.arrival_ms <= now_ms]
        arrived.sort(key=lambda m: (m.start_ms, m.sequence))

        captured: Set[Piece] = set()
        for motion in arrived:
            if motion.piece in captured:
                continue  # captured (and vacated) before its own motion resolved
            self._board.remove(motion.source)
            occupant = self._board.piece_at(motion.target)
            if occupant is not None:
                captured.add(occupant)  # this piece is taken; cancel its motion below
                if occupant.piece_type.is_king:
                    self._game_over = True  # capturing a king ends the game
            self._board.place(motion.target, motion.piece)
            motion.piece.state = PieceState.IDLE

        # Keep only motions still in flight whose piece was not captured.
        self._motions = [
            m
            for m in self._motions
            if m.arrival_ms > now_ms and m.piece not in captured
        ]
