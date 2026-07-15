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

Collisions: two moving pieces "meet" either on the same cell at overlapping times or
by swapping head-on into each other's cell (crossing between cells). Each motion's
``cell_timeline`` gives its per-cell windows. On a shared cell the piece that arrives
*later* is the active one: it captures an enemy already there and continues, or — if
that piece is a friend — cannot enter and stops one cell short. A head-on swap
crosses between cells and so is always simultaneous; like any exact tie it is settled
in favour of the piece that started first. This mid-path pass runs first, while every
mover still sits on its origin; only capturing a *settled* piece on a destination is
left to the arrival step.

The arbiter knows the board, positions, and time, but not chess legality (judged by
the RuleEngine before an action starts), pixels, or the text format.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Set, Tuple

from kfchess.engine.events import GameObserver
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

    def cell_timeline(self) -> List[Tuple[Position, int, int]]:
        """The cells this motion occupies over time, each as ``(cell, enter_ms,
        leave_ms)`` with a half-open ``[enter_ms, leave_ms)`` window.

        A straight-line slide (K/R/B/Q/P) steps through every cell from ``source`` to
        ``target``, spending an equal time-slice in each. A jump (the knight — a
        non-straight ``source``->``target``) passes through no cells in between: it
        holds ``source`` until arrival, then ``target``.

        Windows are half-open: a piece that *enters* a cell exactly as another
        *leaves* it does not count as sharing it. Two enemies whose windows on a cell
        overlap have "met" there — the basis for the mid-path capture rule.
        """
        d_row = self.target.row - self.source.row
        d_col = self.target.col - self.source.col
        distance = max(abs(d_row), abs(d_col))
        span = self.arrival_ms - self.start_ms
        if distance == 0:
            return [(self.source, self.start_ms, self.arrival_ms)]

        is_straight = d_row == 0 or d_col == 0 or abs(d_row) == abs(d_col)
        if not is_straight:  # a knight-style jump: origin, then destination, no path
            return [
                (self.source, self.start_ms, self.arrival_ms),
                (self.target, self.arrival_ms, self.arrival_ms + span),
            ]

        step_row = (d_row > 0) - (d_row < 0)
        step_col = (d_col > 0) - (d_col < 0)
        slice_ms = span // distance
        timeline = []
        for k in range(distance + 1):
            cell = Position(
                self.source.row + step_row * k, self.source.col + step_col * k
            )
            enter = self.start_ms + slice_ms * k
            timeline.append((cell, enter, enter + slice_ms))
        return timeline


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
    """A piece that just landed and is unavailable to move until ``ready_ms``.

    ``started_ms`` and ``duration_ms`` let the graphics layer draw a gauge that drains
    over the cooldown (a move and a jump landing use different durations).
    """

    piece: Piece
    ready_ms: int
    started_ms: int
    duration_ms: int


class RealTimeArbiter:
    """Tracks active motions and jumps and applies them as time advances."""

    def __init__(
        self,
        board: Board,
        ms_per_cell: int,
        promotion: Promotion,
        jump_duration_ms: int,
        cooldown_ms: int,
        jump_cooldown_ms: int = 0,
        observers: Optional[Sequence[GameObserver]] = None,
    ) -> None:
        self._board = board
        self._ms_per_cell = ms_per_cell
        self._promotion = promotion
        self._jump_duration_ms = jump_duration_ms
        self._cooldown_ms = cooldown_ms
        self._jump_cooldown_ms = jump_cooldown_ms
        # Shared with the GameEngine so captures (here) and move-starts (there) reach
        # the same listeners. Empty by default, so the text path emits to no one.
        self._observers = observers if observers is not None else []
        self._motions: List[Motion] = []
        self._jumps: List[Jump] = []
        self._cooldowns: List[Cooldown] = []
        self._settle_ms: Dict[Position, int] = {}  # when the piece on a cell settled
        self._next_sequence = 0
        self._game_over = False

    @property
    def is_game_over(self) -> bool:
        """True once a king has been captured (the game has ended)."""
        return self._game_over

    def cooldown_progress(self, now_ms: int) -> Dict[Piece, float]:
        """Each cooling piece mapped to its *remaining* cooldown fraction (1.0 -> 0.0).

        A rendering aid for the draining cooldown gauge; pieces with no (zero-length)
        cooldown are omitted.
        """
        progress: Dict[Piece, float] = {}
        for cooldown in self._cooldowns:
            if cooldown.duration_ms <= 0:
                continue
            remaining = (cooldown.ready_ms - now_ms) / cooldown.duration_ms
            progress[cooldown.piece] = max(0.0, min(1.0, remaining))
        return progress

    def _notify_capture(self, victim: Piece) -> None:
        """Tell observers a piece was captured, and end the game if it was a king."""
        for observer in self._observers:
            observer.on_capture(victim)
        if victim.piece_type.is_king:
            self._end_game()

    def _end_game(self) -> None:
        """Mark the game over and notify observers once (idempotent)."""
        if not self._game_over:
            self._game_over = True
            for observer in self._observers:
                observer.on_game_over()

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
        self._settle_ms.pop(source, None)  # it is no longer settled on its origin
        piece.state = PieceState.MOVING

    def start_jump(self, piece: Piece, cell: Position, now_ms: int) -> None:
        """Make ``piece`` jump in place on ``cell``, airborne until the duration passes."""
        self._jumps.append(Jump(piece, cell, now_ms + self._jump_duration_ms))
        piece.state = PieceState.JUMPING

    def resolve(self, now_ms: int) -> None:
        """Resolve mid-path captures, then apply arrivals and land finished jumps.

        Order matters: pieces that *met on the way* (two enemies sharing a cell at
        overlapping times) are eaten first, while every mover still sits on its
        origin, before any arrival relocates a piece.
        """
        self._resolve_path_collisions(now_ms)
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
                self._notify_capture(motion.piece)
                self._land(defender, now_ms)
                continue

            self._board.remove(motion.source)
            occupant = self._board.piece_at(motion.target)
            if occupant is not None and occupant.color == motion.piece.color:
                # A same-colour piece reached the destination first: you cannot land
                # on your own, so stop one cell short instead of capturing it.
                stop_cell = self._cell_before(motion, motion.target)
                self._board.place(stop_cell, motion.piece)
                self._settle_ms[stop_cell] = now_ms
                self._begin_cooldown(motion.piece, now_ms, self._cooldown_ms)
                continue
            if occupant is not None:
                captured.add(occupant)  # this piece is taken; cancel its motion below
                self._notify_capture(occupant)  # ends the game too if it was a king
            self._board.place(motion.target, motion.piece)
            self._settle_ms[motion.target] = now_ms
            self._begin_cooldown(motion.piece, now_ms, self._cooldown_ms)
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
                self._land(jump.piece, now_ms)

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

    def _resolve_path_collisions(self, now_ms: int) -> None:
        """Resolve pieces that meet mid-path, earliest meeting first, until none is
        left at or before ``now_ms``.

        Two motions "meet" when they share a cell during overlapping windows. The
        piece that reaches that cell *later* is the active one: against an enemy
        already there it captures it and keeps moving (``_eat``); against a friend it
        cannot enter and stops one cell short (``_block``). Repeating matters — a
        winner that continues can meet a further piece down its path.
        """
        while True:
            event = self._earliest_collision(now_ms)
            if event is None:
                return
            _at, kind, motion, cell = event
            if kind == "eat":
                self._eat(motion)  # two movers meet: the later one eats the earlier
            elif kind == "eat_settled":
                self._eat_settled(cell)  # a mover captures a settled piece and continues
            else:  # "block": the later mover stops one cell short of a friend
                self._block(motion, cell, _at)

    def _earliest_collision(self, now_ms: int) -> Optional[tuple]:
        """The earliest mid-path meeting among the active motions at or before
        ``now_ms``, as ``(at_ms, kind, motion, cell)`` — or ``None``."""
        best: Optional[tuple] = None
        motions = self._motions
        for i in range(len(motions)):
            for j in range(i + 1, len(motions)):
                event = self._collision_event(motions[i], motions[j], now_ms)
                if event is not None and (best is None or event[0] < best[0]):
                    best = event
        for motion in motions:
            event = self._settled_collision_event(motion, now_ms)
            if event is not None and (best is None or event[0] < best[0]):
                best = event
        return best

    @staticmethod
    def _collision_event(a: Motion, b: Motion, now_ms: int) -> Optional[tuple]:
        """The earliest meeting of ``a`` and ``b`` at or before ``now_ms``, as
        ``(at_ms, kind, motion, cell)`` — or ``None``.

        Two motions meet either on a *shared cell* (overlapping windows) or in a
        head-on *swap* into each other's cell (crossing between cells). ``kind`` is
        ``"eat"`` (``motion`` is the piece captured) or ``"block"`` (``motion`` stops
        just before ``cell``). On a shared cell the later entrant is the active one;
        an equal entry time, and every swap (a between-cells crossing is always
        simultaneous), go to the piece that *started* first, so the other yields.
        """
        same_colour = a.piece.color == b.piece.color
        timeline_a = a.cell_timeline()
        timeline_b = b.cell_timeline()
        started_second = a if a.start_ms > b.start_ms else b  # yields on any tie/swap
        best: Optional[tuple] = None
        for i, (cell_a, enter_a, leave_a) in enumerate(timeline_a):
            for j, (cell_b, enter_b, leave_b) in enumerate(timeline_b):
                start = max(enter_a, enter_b)
                if start >= min(leave_a, leave_b) or start > now_ms:
                    continue  # windows do not overlap, or the meeting is still future
                if cell_a == cell_b:
                    if enter_a == enter_b:
                        motion, cell = started_second, cell_a
                    elif same_colour:  # later entrant cannot enter; it stops short
                        motion, cell = (a if enter_a > enter_b else b), cell_a
                    else:  # later entrant eats the piece already there
                        motion, cell = (b if enter_a > enter_b else a), cell_a
                elif (
                    RealTimeArbiter._are_adjacent(cell_a, cell_b)
                    and i + 1 < len(timeline_a)
                    and timeline_a[i + 1][0] == cell_b
                    and j + 1 < len(timeline_b)
                    and timeline_b[j + 1][0] == cell_a
                ):
                    # head-on swap: each is moving into the other's cell. The yielder
                    # stops just before the cell it was entering (the other's cell).
                    motion = started_second
                    cell = cell_b if motion is a else cell_a
                else:
                    continue
                kind = "block" if same_colour else "eat"
                if best is None or start < best[0]:
                    best = (start, kind, motion, cell)
        return best

    @staticmethod
    def _are_adjacent(x: Position, y: Position) -> bool:
        """True if ``x`` and ``y`` are one step apart (including diagonally)."""
        return max(abs(x.row - y.row), abs(x.col - y.col)) == 1

    def _settled_collision_event(
        self, a: Motion, now_ms: int
    ) -> Optional[tuple]:
        """The earliest *transit* cell where ``a`` runs into a piece that had already
        settled on its path, at or before ``now_ms`` — as ``(at_ms, kind, motion,
        cell)`` or ``None``.

        ``kind`` is ``"eat_settled"`` (``a`` is the later arriver, captures the
        settled enemy and keeps going) or ``"block"`` (``a`` stops one cell short of a
        settled friend). The destination itself is left to the arrival step, so only
        the cells *before* the target are considered. The settled piece must have
        arrived *before* ``a`` reached the cell, else ``a`` passed first and they
        never shared it.
        """
        for cell, enter, _leave in a.cell_timeline()[:-1]:  # transit cells only
            if enter > now_ms:
                break  # a has not reached this cell yet (later cells are later still)
            settled_ms = self._settle_ms.get(cell)
            if settled_ms is None or settled_ms > enter:
                continue  # nothing settled here, or it settled after a passed through
            occupant = self._board.piece_at(cell)
            if occupant is None or occupant is a.piece:
                continue
            if occupant.state in (PieceState.MOVING, PieceState.JUMPING):
                continue  # only a truly settled piece blocks/is eaten mid-path
            if occupant.color == a.piece.color:
                return (enter, "block", a, cell)
            return (enter, "eat_settled", a, cell)
        return None

    def _eat_settled(self, cell: Position) -> None:
        """Capture the settled piece on ``cell`` in passing; the mover keeps its
        motion and continues. Clears the victim's cooldown and settle record."""
        victim = self._board.remove(cell)
        self._settle_ms.pop(cell, None)
        if victim is not None:
            self._cooldowns = [c for c in self._cooldowns if c.piece is not victim]
            self._notify_capture(victim)  # ends the game too if it was a king

    def _eat(self, eaten: Motion) -> None:
        """Remove an eaten piece (still on its origin) and drop its motion."""
        self._board.remove(eaten.source)
        self._notify_capture(eaten.piece)  # ends the game too if it was a king
        self._motions = [m for m in self._motions if m is not eaten]

    def _block(self, blocked: Motion, cell: Position, at_ms: int) -> None:
        """Stop ``blocked`` on the cell just before ``cell`` on its own path: land it
        there (on cooldown from ``at_ms``) and drop its motion."""
        stop_cell = self._cell_before(blocked, cell)
        self._board.remove(blocked.source)
        self._board.place(stop_cell, blocked.piece)
        self._settle_ms[stop_cell] = at_ms
        self._begin_cooldown(blocked.piece, at_ms, self._cooldown_ms)
        self._motions = [m for m in self._motions if m is not blocked]

    @staticmethod
    def _cell_before(motion: Motion, cell: Position) -> Position:
        """The cell ``motion`` occupies just before ``cell`` on its path (its own
        source if ``cell`` is the first step)."""
        timeline = motion.cell_timeline()
        for index, (occupied, _enter, _leave) in enumerate(timeline):
            if occupied == cell:
                return timeline[index - 1][0] if index > 0 else motion.source
        return motion.source  # cell is not on the path (should not happen)

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

    def _begin_cooldown(self, piece: Piece, now_ms: int, duration_ms: int) -> None:
        """Put a just-landed piece on cooldown for ``duration_ms``.

        The piece is marked ``COOLDOWN`` and freed back to ``IDLE`` by ``resolve``
        once the cooldown elapses. With ``duration_ms == 0`` the ready time equals
        ``now_ms``, so ``resolve`` frees it in the same pass — i.e. no cooldown.
        """
        piece.state = PieceState.COOLDOWN
        self._cooldowns.append(
            Cooldown(piece, now_ms + duration_ms, now_ms, duration_ms)
        )

    def _land(self, piece: Piece, now_ms: int) -> None:
        """Land a jumping piece in place, dropping its jump and starting its (short)
        jump cooldown before it can act again."""
        self._jumps = [j for j in self._jumps if j.piece is not piece]
        self._begin_cooldown(piece, now_ms, self._jump_cooldown_ms)
