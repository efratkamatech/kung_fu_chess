"""ClientGameState: rebuild the game from deltas, and hand the renderer a snapshot.

The server no longer sends a picture of the whole board twenty times a second; it sends
one small message per thing that actually happened (see the delta section of
:mod:`kfchess.shared.protocol`). Something on the client has to turn that stream back
into a board — and that is all this does::

    NetClient  --deltas-->  ClientGameState  --snapshot(now)-->  snapshot_view.py

Because it produces a :class:`~kfchess.shared.snapshot.GameSnapshot`, exactly the shape
the renderer, the HUD, and the click controller already read, **nothing downstream
changes**: the drawing code cannot tell whether the snapshot arrived whole from the
server or was rebuilt here.

Three ideas carry the whole file:

- **Pieces are named, not located.** Each piece keeps its ``piece_id`` for life, so a
  delta about a piece in flight — which is between squares and has no cell to name — is
  still unambiguous. A piece is in exactly one of two places here: settled on a cell, or
  in flight.
- **Motion is arithmetic, not authority.** A :class:`~kfchess.shared.protocol.MoveStarted`
  gives two endpoints and two times; every frame in between is interpolated with the
  same formula :meth:`kfchess.engine.arbiter.Motion.position_at` uses on the server. What
  *happens* — captures, blocks, promotions, game over — is only ever announced by the
  server and obeyed unconditionally.
- **The counting is not re-implemented.** The scoreboard, the moves log, and the phase
  banner are the same three observers the server runs (:mod:`kfchess.observers`), fed
  here by republishing each delta as the bus event it came from. So the two sides tally
  and format by the same code rather than by two rules that agree until one is edited.

A full :class:`~kfchess.shared.protocol.State` resets everything, which is what seating,
reconnect, and the periodic resync send. One gap is deliberate there: a snapshot reports
a flying piece's *position* but not its destination, so a client meeting a flight for the
first time mid-air (a spectator, or a returning player) holds it still until the server
says where it landed. A flight this client already knows keeps its own timing across the
reset, so the ten-second resync never interrupts a move in progress.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from kfchess.bus import events as bus_events
from kfchess.bus.event_bus import EventBus
from kfchess.config import COOLDOWN_MS, HUD_MOVES_VISIBLE
from kfchess.model.color import Color
from kfchess.model.piece import Piece, PieceState
from kfchess.model.piece_type import PieceTypeRegistry, standard_piece_types
from kfchess.model.position import Position
from kfchess.observers import GameBanner, MovesLog, ScoreBoard
from kfchess.shared import protocol
from kfchess.shared.algebraic import square_to_position
from kfchess.shared.snapshot import CellView, GameSnapshot, MovingView
from kfchess.shared.tokens import token_to_piece

# The two seats, in the order the snapshot reports them (as on the server).
_COLORS = (Color.WHITE, Color.BLACK)

# Every server -> client message that describes the *game*, as opposed to this client's
# place in it (Welcome, Seated, Notice, Rejected) or a one-shot perception (Event).
GAME_MESSAGES = (
    protocol.State,
    protocol.MoveStarted,
    protocol.Settled,
    protocol.Captured,
    protocol.CooldownDone,
    protocol.GameOver,
    protocol.Disconnected,
    protocol.Reconnected,
)


def monotonic_ms() -> int:
    """The local clock in milliseconds — a duration source, not a wall-clock time."""
    return time.monotonic_ns() // 1_000_000


class ServerClock:
    """The client's running estimate of the server's clock, in server milliseconds.

    Every delta is stamped on the *server's* clock, and interpolating between two stamps
    needs a "now" on that same timeline. So each message re-anchors the estimate — the
    server was at T when this arrived — and the local monotonic clock carries it forward
    between messages.

    Once anchored the estimate only ever moves forward. Stamps do not arrive in order (a
    :class:`~kfchess.shared.protocol.CooldownDone` carries the moment a cooldown *ended*,
    which is older than the tick that noticed it), and a piece that jumped backwards
    mid-flight would look far worse than one drawn a few milliseconds late.

    **Until the first stamp arrives there is nothing to move forward from.** The reading
    below starts at zero when this client is built and climbs with the local clock, while
    the server's stamps count the *game's* age from when its session was created. The two
    share no origin: a client that sat in the lobby for a minute before its game began is
    a minute "ahead" of a server it has never heard from. Letting the forward-only rule
    defend that placeholder rejects the first real anchor, and every one after it — the
    offset then never washes out, and once it exceeds a move's flight time every piece is
    drawn already landed and nothing on that screen ever animates again. So the first
    stamp is obeyed whichever way it points; the rule starts once there is a real anchor
    to protect.
    """

    __slots__ = ("_monotonic_ms", "_server_ms", "_local_ms", "_anchored")

    def __init__(self, monotonic: Callable[[], int] = monotonic_ms) -> None:
        self._monotonic_ms = monotonic
        self._server_ms = 0
        self._local_ms = monotonic()
        # False until a server stamp has been seen: what `now_ms` reads before that is a
        # placeholder on an unrelated origin, not an estimate worth defending.
        self._anchored = False

    @property
    def now_ms(self) -> int:
        """Where the server's clock is now, as best this client can tell."""
        return self._server_ms + (self._monotonic_ms() - self._local_ms)

    def sync(self, server_ms: int) -> None:
        """Re-anchor on a time the server just reported.

        Always for the first stamp, which establishes the timeline; after that only when
        it is not already behind.
        """
        if self._anchored and server_ms < self.now_ms:
            return
        self._anchored = True
        self._server_ms = server_ms
        self._local_ms = self._monotonic_ms()


@dataclass
class _Flight:
    """A piece in flight: where it left, where it is due, and when.

    ``source``/``target`` are fractional ``(row, col)`` rather than cells because a
    flight picked up from a snapshot starts wherever the snapshot found it, mid-square.
    """

    token: str
    source: Tuple[float, float]
    target: Tuple[float, float]
    start_ms: int
    arrival_ms: int

    def position_at(self, now_ms: int) -> Tuple[float, float]:
        """Where this piece is at ``now_ms``, clamped to its endpoints.

        The same arithmetic as :meth:`kfchess.engine.arbiter.Motion.position_at`, which
        is what makes the client's picture agree with the server's between deltas.
        """
        span = self.arrival_ms - self.start_ms
        if span <= 0:
            return self.target
        progress = min(1.0, max(0.0, (now_ms - self.start_ms) / span))
        return (
            self.source[0] + (self.target[0] - self.source[0]) * progress,
            self.source[1] + (self.target[1] - self.source[1]) * progress,
        )


@dataclass
class _Settled:
    """A piece at rest on ``cell``, free to move again at ``ready_ms``."""

    token: str
    cell: Position
    ready_ms: int
    cooldown_ms: int

    def view(self, piece_id: int, now_ms: int) -> CellView:
        """This piece as the renderer reads it: its state and cooldown gauge at ``now_ms``.

        The gauge is derived rather than waited for, so it drains smoothly between
        messages; the arithmetic is
        :meth:`kfchess.engine.arbiter.RealTimeArbiter.cooldown_progress`, and a
        :class:`~kfchess.shared.protocol.CooldownDone` closes it authoritatively by
        moving ``ready_ms`` to the moment it really ended.
        """
        remaining = self.ready_ms - now_ms
        if self.cooldown_ms <= 0 or remaining <= 0:
            return CellView(self.token, PieceState.IDLE.name, 0.0, piece_id)
        fraction = min(1.0, remaining / self.cooldown_ms)
        return CellView(self.token, PieceState.COOLDOWN.name, fraction, piece_id)


class ClientGameState:
    """The board as this client believes it, folded together one delta at a time."""

    def __init__(
        self,
        clock: Optional[ServerClock] = None,
        piece_types: Optional[PieceTypeRegistry] = None,
    ) -> None:
        self._clock = clock if clock is not None else ServerClock()
        self._piece_types = piece_types or standard_piece_types()
        self._settled: Dict[int, _Settled] = {}
        self._flights: Dict[int, _Flight] = {}
        self._names: Dict[Color, str] = {}
        self._ratings: Dict[Color, int] = {}
        self._room_id: Optional[str] = None
        self._winner: Optional[Color] = None
        self._disconnected: Optional[Color] = None
        self._resign_at_ms = 0
        # Everything below arrives with the first full snapshot: the board's size, the
        # running scores, and the log lines. Until one does there is nothing to draw and
        # nothing to fold a delta into, which is what ``_rows is None`` means throughout.
        self._rows: Optional[int] = None
        self._cols = 0
        self._bus = EventBus()
        self._score = ScoreBoard()
        self._log = MovesLog(0)
        self._banner = GameBanner()

    # --- folding messages in --------------------------------------------------

    def apply(self, message) -> None:
        """Fold one server message into the state; anything else is ignored."""
        if isinstance(message, protocol.State):
            self.reset(message.snapshot)
        elif self._rows is None:
            return  # a delta before the first snapshot: nothing to fold it into
        elif isinstance(message, protocol.MoveStarted):
            self._on_move_started(message)
        elif isinstance(message, protocol.Settled):
            self._on_settled(message)
        elif isinstance(message, protocol.Captured):
            self._on_captured(message)
        elif isinstance(message, protocol.CooldownDone):
            self._on_cooldown_done(message)
        elif isinstance(message, protocol.GameOver):
            self._on_game_over(message)
        elif isinstance(message, protocol.Disconnected):
            self._on_disconnected(message)
        elif isinstance(message, protocol.Reconnected):
            self._on_reconnected(message)

    def reset(self, snapshot: GameSnapshot) -> None:
        """Replace everything with a full snapshot — seating, reconnect, or resync."""
        self._clock.sync(snapshot.now_ms)
        self._rows, self._cols = snapshot.rows, snapshot.cols
        self._names = dict(snapshot.names)
        self._ratings = dict(snapshot.ratings)
        self._room_id = snapshot.room_id
        self._winner = snapshot.winner
        self._disconnected = snapshot.disconnected
        self._resign_at_ms = snapshot.now_ms + snapshot.resign_ms
        self._settled = {
            cell.piece_id: _Settled(
                cell.token,
                Position(row, col),
                # A snapshot reports how much of the cooldown is *left*, as a fraction;
                # the length itself is a constant both sides already know.
                snapshot.now_ms + round(cell.cooldown * COOLDOWN_MS),
                COOLDOWN_MS,
            )
            for row, cells in enumerate(snapshot.cells)
            for col, cell in enumerate(cells)
            if cell is not None
        }
        self._flights = {
            view.piece_id: self._flight_for(view, snapshot.now_ms)
            for view in snapshot.moving
        }
        self._reseat_observers(snapshot)

    def _flight_for(self, view: MovingView, now_ms: int) -> _Flight:
        """The flight behind one of a snapshot's moving pieces.

        Kept as it is if this client started it — its endpoints and timing are still
        good, and re-deriving them would only make the piece stutter every resync. A
        flight met for the first time here (a spectator or a returning player, arriving
        mid-air) has no destination in the snapshot, so it is held where it was found
        until the server says where it landed.
        """
        known = self._flights.get(view.piece_id)
        if known is not None:
            return known
        return _Flight(view.token, (view.row, view.col), (view.row, view.col), now_ms, now_ms)

    def _reseat_observers(self, snapshot: GameSnapshot) -> None:
        """Point a fresh scoreboard, log, and banner at what the snapshot reports.

        Fresh ones, on a fresh bus, so a resync never leaves an old subscription behind;
        seeded rather than replayed, because a snapshot carries the totals but not the
        events that produced them.
        """
        self._bus = EventBus()
        self._score = ScoreBoard()
        self._log = MovesLog(snapshot.rows)
        self._banner = GameBanner()
        for observer in (self._score, self._log, self._banner):
            observer.subscribe(self._bus)
        self._score.seed(snapshot.scores)
        self._log.seed(snapshot.logs)
        self._banner.seed(snapshot.phase)

    def _on_move_started(self, message: protocol.MoveStarted) -> None:
        self._clock.sync(message.start_ms)
        source = self._cell(message.from_sq)
        target = self._cell(message.to_sq)
        self._settled.pop(message.piece_id, None)  # it is between squares now
        self._flights[message.piece_id] = _Flight(
            message.token,
            (float(source.row), float(source.col)),
            (float(target.row), float(target.col)),
            message.start_ms,
            message.arrival_ms,
        )
        self._bus.publish(
            bus_events.MoveStarted(
                self._piece(message.token),
                source,
                target,
                message.start_ms,
                message.arrival_ms,
            )
        )

    def _on_settled(self, message: protocol.Settled) -> None:
        self._clock.sync(message.at_ms)
        self._flights.pop(message.piece_id, None)
        self._settled[message.piece_id] = _Settled(
            message.token,  # what it *became*, if it promoted on landing
            self._cell(message.at_sq),
            message.at_ms + message.cooldown_ms,
            message.cooldown_ms,
        )

    def _on_captured(self, message: protocol.Captured) -> None:
        self._clock.sync(message.at_ms)
        # Wherever it was — settled or in flight — it is off the board now.
        self._settled.pop(message.piece_id, None)
        self._flights.pop(message.piece_id, None)
        self._bus.publish(
            bus_events.Captured(self._piece(message.token), message.at_ms)
        )

    def _on_cooldown_done(self, message: protocol.CooldownDone) -> None:
        self._clock.sync(message.at_ms)
        settled = self._settled.get(message.piece_id)
        if settled is not None:  # it may have been captured while cooling down
            settled.ready_ms = message.at_ms

    def _on_game_over(self, message: protocol.GameOver) -> None:
        self._clock.sync(message.at_ms)
        self._winner = message.winner
        self._ratings.update(message.ratings)  # empty for an unrated game
        self._bus.publish(bus_events.GameOver(message.winner))

    def _on_disconnected(self, message: protocol.Disconnected) -> None:
        # The deadline, not a countdown: the remaining time is read off the clock, so it
        # keeps draining between messages instead of waiting to be told again.
        self._disconnected = message.color
        self._resign_at_ms = message.resign_at_ms

    def _on_reconnected(self, message: protocol.Reconnected) -> None:
        self._disconnected = None
        self._resign_at_ms = 0

    # --- reading it back out --------------------------------------------------

    def current(self) -> Optional[GameSnapshot]:
        """The snapshot at this client's estimate of the server's clock."""
        return self.snapshot(self._clock.now_ms)

    def snapshot(self, now_ms: int) -> Optional[GameSnapshot]:
        """The whole game as of ``now_ms``, or ``None`` before the first full snapshot.

        Built fresh on each call because two of its parts — where a flying piece is, and
        how much cooldown is left — are functions of the time it is asked for.
        """
        if self._rows is None:
            return None
        cells: List[List[Optional[CellView]]] = [
            [None] * self._cols for _ in range(self._rows)
        ]
        for piece_id, settled in self._settled.items():
            cells[settled.cell.row][settled.cell.col] = settled.view(piece_id, now_ms)
        moving = []
        for piece_id, flight in self._flights.items():
            row, col = flight.position_at(now_ms)
            moving.append(MovingView(flight.token, row, col, piece_id))
        return GameSnapshot(
            rows=self._rows,
            cols=self._cols,
            cells=cells,
            moving=moving,
            scores={color: self._score.score(color) for color in _COLORS},
            logs={
                color: self._log.recent(color, HUD_MOVES_VISIBLE) for color in _COLORS
            },
            names=dict(self._names),
            ratings=dict(self._ratings),
            phase=self._banner.phase,
            winner=self._winner,
            now_ms=now_ms,
            disconnected=self._disconnected,
            resign_ms=(
                max(0, self._resign_at_ms - now_ms)
                if self._disconnected is not None
                else 0
            ),
            room_id=self._room_id,
        )

    # --- small conversions ----------------------------------------------------

    def _cell(self, square: str) -> Position:
        """The cell a delta's square names, e.g. ``"a1"`` on a three-row board."""
        return square_to_position(square, self._rows)

    def _piece(self, token: str) -> Piece:
        """A model piece for ``token``, for the observers to read colour and value off."""
        return token_to_piece(token, self._piece_types)
