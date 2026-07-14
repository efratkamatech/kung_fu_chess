"""RealTimeArbiter: moves take time, pieces collide, and pieces can jump in place.

Owns the in-flight motions, the active jumps, and the landing cooldowns.

Motions: starting one records where a piece is going, when it started, and when it
arrives (``now + distance * ms_per_cell``); the piece stays at its origin, marked
MOVING, until then. ``resolve`` applies arrived motions in start order (see the
collision note below).

Jumps: a jump keeps a piece airborne *in place* on its cell (marked JUMPING) until
``now + jump_duration_ms``. While airborne, if an enemy moving piece arrives on that
cell (arrival time at or before the jump's end), the jumper captures the arriver
instead of the other way round; the jumper does not move. If nothing arrives, the
jump lands (returns to IDLE) with the piece unmoved.

Cooldowns: when a motion lands, the piece is marked COOLDOWN until
``now + cooldown_ms`` instead of going straight to IDLE, so it cannot start a new
move until the cooldown elapses (the RuleEngine rejects a COOLDOWN piece the same
way it rejects a MOVING one). ``resolve`` frees cooled pieces back to IDLE as time
passes. A ``cooldown_ms`` of 0 frees the piece in the same pass — i.e. no cooldown.

Collisions: because a moving piece stays at its origin until it arrives, two enemies
crossing toward each other's squares are resolved by resolving arrivals in start
order and cancelling a captured piece's motion — the one that started first wins.

The arbiter knows the board, positions, and time, but not chess legality (judged by
the RuleEngine before an action starts), pixels, or the text format.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Set, Tuple

from kfchess.model.board import Board
from kfchess.model.piece import Piece, PieceState
from kfchess.model.position import Position
from kfchess.rules.promotion import Promotion


@dataclass(frozen=True)
class Motion:
    """A piece in flight, with its timing and a sequence number for ordering."""

    piece: Piece
    source: Position
    target: Position
    start_ms: int
    arrival_ms: int
    sequence: int  # order the motion was started (tie-breaker for "started first")

    def position_at(self, now_ms: int) -> Tuple[float, float]:
        """This piece's *fractional* (row, col) at ``now_ms`` along its straight-line
        path from ``source`` to ``target``.

        Clamped to the endpoints: before the motion starts it reads as ``source``,
        and once it has arrived (or later) as ``target``. Progress is taken from the
        motion's own ``start_ms``/``arrival_ms`` span, so the speed matches whatever
        the arbiter assigned when the motion began. Read-only: it computes, never
        mutates.
        """
        span = self.arrival_ms - self.start_ms
        if span <= 0:
            return (float(self.target.row), float(self.target.col))
        progress = min(1.0, max(0.0, (now_ms - self.start_ms) / span))
        row = self.source.row + (self.target.row - self.source.row) * progress
        col = self.source.col + (self.target.col - self.source.col) * progress
        return (row, col)


@dataclass(frozen=True)
class MovingPiece:
    """A read-only view of one in-flight piece: where it is now and its endpoints.

    Produced by ``RealTimeArbiter.moving_pieces`` for callers that render motion.
    ``position`` is a *fractional* cell — e.g. (3.5, 4.0) is halfway between two
    cells — not a board cell. It carries no way to mutate the underlying motion.
    """

    piece: Piece
    position: Tuple[float, float]
    source: Position
    target: Position


@dataclass(frozen=True)
class Jump:
    """A piece airborne in place on ``cell`` until ``end_ms``."""

    piece: Piece
    cell: Position
    end_ms: int


@dataclass(frozen=True)
class Cooldown:
    """A piece that just landed and is unavailable to move until ``ready_ms``."""

    piece: Piece
    ready_ms: int


class RealTimeArbiter:
    """Tracks active motions and jumps and applies them as time advances."""

    def __init__(
        self,
        board: Board,
        ms_per_cell: int,
        promotion: Promotion,
        jump_duration_ms: int,
        cooldown_ms: int,
    ) -> None:
        self._board = board
        self._ms_per_cell = ms_per_cell
        self._promotion = promotion
        self._jump_duration_ms = jump_duration_ms
        self._cooldown_ms = cooldown_ms
        self._motions: List[Motion] = []
        self._jumps: List[Jump] = []
        self._cooldowns: List[Cooldown] = []
        self._next_sequence = 0
        self._game_over = False

    @property
    def is_game_over(self) -> bool:
        """True once a king has been captured (the game has ended)."""
        return self._game_over

    def moving_pieces(self, now_ms: int) -> List[MovingPiece]:
        """A snapshot of every in-flight piece and its interpolated position at
        ``now_ms`` — a read-only overlay for rendering.

        Derived purely from the active motions; it never touches the board. A moving
        piece still sits on its *origin* cell on the board until it arrives, so this
        is where the piece visually *is* mid-flight, not where the board records it.
        """
        return [
            MovingPiece(m.piece, m.position_at(now_ms), m.source, m.target)
            for m in self._motions
        ]

    def start_motion(
        self, piece: Piece, source: Position, target: Position, now_ms: int
    ) -> None:
        """Begin moving ``piece`` from ``source`` to ``target`` starting at ``now_ms``."""
        distance = max(
            abs(target.row - source.row), abs(target.col - source.col)
        )
        arrival_ms = now_ms + distance * self._ms_per_cell
        self._motions.append(
            Motion(piece, source, target, now_ms, arrival_ms, self._next_sequence)
        )
        self._next_sequence += 1
        piece.state = PieceState.MOVING

    def start_jump(self, piece: Piece, cell: Position, now_ms: int) -> None:
        """Make ``piece`` jump in place on ``cell``, airborne until the duration passes."""
        self._jumps.append(Jump(piece, cell, now_ms + self._jump_duration_ms))
        piece.state = PieceState.JUMPING

    def resolve(self, now_ms: int) -> None:
        """Apply arrivals (in start order) and land jumps whose window has ended."""
        arrived = [m for m in self._motions if m.arrival_ms <= now_ms]
        arrived.sort(key=lambda m: (m.start_ms, m.sequence))

        captured: Set[Piece] = set()
        for motion in arrived:
            if motion.piece in captured:
                continue  # captured (and vacated) before its own motion resolved

            defender = self._airborne_defender(
                motion.target, motion.piece, motion.arrival_ms
            )
            if defender is not None:
                # The airborne jumper captures the arriving enemy; it does not move.
                self._board.remove(motion.source)
                captured.add(motion.piece)
                self._land(defender)
                continue

            self._board.remove(motion.source)
            occupant = self._board.piece_at(motion.target)
            if occupant is not None:
                captured.add(occupant)  # this piece is taken; cancel its motion below
                if occupant.piece_type.is_king:
                    self._game_over = True  # capturing a king ends the game
            self._board.place(motion.target, motion.piece)
            self._begin_cooldown(motion.piece, now_ms)
            self._promotion.apply(motion.piece, motion.target, self._board)

        # Keep only motions still in flight whose piece was not captured.
        self._motions = [
            m
            for m in self._motions
            if m.arrival_ms > now_ms and m.piece not in captured
        ]

        # Land any jumps whose airborne window has ended (with nothing to capture).
        for jump in list(self._jumps):
            if jump.end_ms <= now_ms:
                self._land(jump.piece)

        # Free any pieces whose landing cooldown has now elapsed, and forget any
        # cooling piece that was captured in the meantime.
        for cooldown in self._cooldowns:
            if cooldown.ready_ms <= now_ms and cooldown.piece not in captured:
                cooldown.piece.state = PieceState.IDLE
        self._cooldowns = [
            c
            for c in self._cooldowns
            if c.ready_ms > now_ms and c.piece not in captured
        ]

    def _airborne_defender(
        self, cell: Position, arriver: Piece, arrival_ms: int
    ) -> Optional[Piece]:
        """An enemy jumper still airborne on ``cell`` when ``arriver`` reaches it."""
        for jump in self._jumps:
            if (
                jump.cell == cell
                and jump.piece.color != arriver.color
                and arrival_ms <= jump.end_ms
            ):
                return jump.piece
        return None

    def _begin_cooldown(self, piece: Piece, now_ms: int) -> None:
        """Put a just-landed piece on cooldown until ``now_ms + cooldown_ms``.

        The piece is marked ``COOLDOWN`` and freed back to ``IDLE`` by ``resolve``
        once the cooldown elapses. With ``cooldown_ms == 0`` the ready time equals
        ``now_ms``, so ``resolve`` frees it in the same pass — i.e. no cooldown.
        """
        piece.state = PieceState.COOLDOWN
        self._cooldowns.append(Cooldown(piece, now_ms + self._cooldown_ms))

    def _land(self, piece: Piece) -> None:
        """Return a jumping piece to rest, in place, and drop its jump."""
        piece.state = PieceState.IDLE
        self._jumps = [j for j in self._jumps if j.piece is not piece]
