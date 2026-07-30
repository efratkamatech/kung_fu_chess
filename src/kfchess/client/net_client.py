"""NetClient: the client's network half — connect, send commands, receive the game.

The windowed client's cv2 loop runs on the main thread and must never block on the
network, so the socket lives on a background thread with its own asyncio loop. This
class is the bridge between the two threads: the background thread pushes decoded state
*in* (:meth:`handle`), and the main thread reads the latest snapshot *out*
(:meth:`latest` / :attr:`color`) and queues messages to send
(:meth:`queue_command`, :meth:`login`, :meth:`play`, :meth:`create_room`,
:meth:`join_room`) — all guarded by a lock so the two threads never corrupt shared state.

Everything the client sends rides *one* outbound queue as a ready-made protocol object,
so a single sender drains it in order and encodes each message the same way; a new
outbound message type is one more method here, not another queue and sender coroutine.

The decode/store/read logic is synchronous and unit-tested. The thread, the asyncio
loop, and the WebSocket recv/send are the irreducible I/O and are excluded from
coverage, like the cv2 calls in ``img.py``.
"""

from __future__ import annotations

import logging
import queue
import threading
from dataclasses import dataclass
from typing import Optional

from kfchess.client.game_state import GAME_MESSAGES, ClientGameState, ServerClock
from kfchess.model.color import Color
from kfchess.shared.codes import NoticeReason, RejectReason
from kfchess.shared.protocol import (
    CreateRoom,
    Event,
    JoinRoom,
    Login,
    Move,
    Notice,
    Play,
    Rejected,
    Seated,
    Welcome,
    decode,
)
from kfchess.shared.snapshot import GameSnapshot

_log = logging.getLogger(__name__)  # client activity trail; silent until configured

@dataclass(frozen=True)
class MatchResult:
    """The server's answer to a "Play", "create room", or "join room" request.

    It is exactly one of two things, and :attr:`seated` says which: a seat in a game, or
    the reason no game could be started. Build it through :meth:`seat` / :meth:`refused`
    rather than by hand, so the two never blur into each other.

    Note that ``color`` is ``None`` on a seat too — that is a spectator, who is seated
    and watching. Only ``reason`` distinguishes the two outcomes.
    """

    color: Optional[Color] = None
    reason: Optional[NoticeReason] = None

    @classmethod
    def seat(cls, color: Optional[Color]) -> "MatchResult":
        """Placed in a game as ``color`` (``None`` means seated as a spectator)."""
        return cls(color=color)

    @classmethod
    def refused(cls, reason: NoticeReason) -> "MatchResult":
        """No game was started, for this reason; the caller can offer the menu again."""
        return cls(reason=reason)

    @property
    def seated(self) -> bool:
        """Whether this answer placed the client in a game."""
        return self.reason is None


class NetClient:
    """Thread-safe bridge between the cv2 main loop and the background WebSocket.

    Game messages are folded into a :class:`~kfchess.client.game_state.ClientGameState`,
    which is what :meth:`latest` reads a snapshot back out of; everything about *this
    client's* place in the game — its colour, its rating, a refusal, a sound — is kept
    here, where the two threads meet.
    """

    def __init__(self, clock: Optional[ServerClock] = None) -> None:
        self._lock = threading.Lock()
        # The board, rebuilt from the deltas the server sends instead of received whole
        # twenty times a second. ``clock`` is injectable so a test can freeze the
        # interpolation the snapshot is read at.
        self._state = ClientGameState(clock)
        self._color: Optional[Color] = None
        self._rating: Optional[int] = None
        self._room_id: Optional[str] = None
        self._logged_in = False
        self._rejection: Optional[str] = None
        # Every client -> server message waits here as a protocol object, whatever its
        # kind (a Move, Login, Play, CreateRoom or JoinRoom): the network thread pops
        # them in order and encodes each one the same way. Keeping a single queue means
        # a new outbound message type is one more method, not another queue and sender.
        self._outgoing: "queue.Queue" = queue.Queue()
        # One-shot perception events (sound kinds) queued separately from the
        # snapshot/colour/rejection state above: each is consumed exactly once by
        # next_event(), not just "the latest value", since every one matters.
        self._events: "queue.Queue[str]" = queue.Queue()
        # The outcome of each login attempt: None = accepted, else the refusal reason.
        self._login_results: "queue.Queue[Optional[RejectReason]]" = queue.Queue()
        # The answer to each "Play" / room request (a seat, or why there is none).
        self._match_results: "queue.Queue[MatchResult]" = queue.Queue()

    def handle(self, text: str) -> None:
        """Process one incoming wire message: store the snapshot, colour, or rejection.

        Called from the network thread. Garbage or unexpected messages are dropped.
        """
        try:
            message = decode(text)
        except ValueError:
            return
        with self._lock:
            if isinstance(message, GAME_MESSAGES):
                self._state.apply(message)
            elif isinstance(message, Welcome):
                self._color = message.color
                self._rating = message.rating
                self._logged_in = True
                _log.info("login accepted (rating %s)", message.rating)
                self._login_results.put(None)  # login accepted
            elif isinstance(message, Seated):
                self._color = message.color  # put in a game as this colour (None = watcher)
                self._room_id = message.room_id  # set when seated via a room
                _log.info("seated as %s in room %s", message.color, message.room_id)
                self._match_results.put(MatchResult.seat(message.color))
            elif isinstance(message, Notice):
                # A lobby notice answers a pending Play / room request.
                _log.info("lobby notice: %s", message.reason)
                self._match_results.put(MatchResult.refused(message.reason))
            elif isinstance(message, Rejected):
                # Before logging in, a rejection means the login was refused (bad
                # password); after, it means a move was refused.
                _log.info("rejected: %s", message.reason)
                if self._logged_in:
                    self._rejection = message.reason
                else:
                    self._login_results.put(message.reason)
            elif isinstance(message, Event):
                self._events.put(message.kind)

    def queue_command(self, cmd: str) -> None:
        """Queue a move command (e.g. ``"WQe2e5"``) for the network thread to send."""
        self._outgoing.put(Move(cmd))

    def login(self, username: str, password: str) -> None:
        """Queue a login attempt; the network thread sends it as a Login message.

        May be called more than once (retry after a bad password) — each attempt's
        outcome is reported by one :meth:`wait_for_login`.
        """
        self._outgoing.put(Login(username, password))

    def wait_for_login(self, timeout: Optional[float] = None) -> Optional[RejectReason]:
        """Block until the server answers a login attempt.

        Returns ``None`` if it was accepted, or the :class:`RejectReason` it was refused
        for (in practice ``BAD_PASSWORD``) — the caller can then prompt again and retry.
        """
        return self._login_results.get(timeout=timeout)

    def play(self) -> None:
        """Queue a "Play" request; the network thread sends it as a Play message.

        The answer (matched, or no opponent) is reported by one :meth:`wait_for_match`.
        """
        self._outgoing.put(Play())

    def wait_for_match(self, timeout: Optional[float] = None) -> MatchResult:
        """Block until the server answers a "Play", "create room", or "join room" request.

        Returns a :class:`MatchResult`: a seat once placed in a game, or a refusal
        carrying the reason, so the caller can prompt the player to try again.
        """
        return self._match_results.get(timeout=timeout)

    def create_room(self) -> None:
        """Queue a "create room" request; the answer comes via :meth:`wait_for_match`."""
        self._outgoing.put(CreateRoom())

    def join_room(self, room_id: str) -> None:
        """Queue a "join room" request; the answer comes via :meth:`wait_for_match`."""
        self._outgoing.put(JoinRoom(room_id))

    def next_event(self) -> Optional[str]:
        """The next queued sound-kind event (e.g. ``"capture"``), or ``None`` if none
        are waiting. Called once per frame by the render loop to drain the queue."""
        try:
            return self._events.get_nowait()
        except queue.Empty:
            return None

    def next_outgoing(self, timeout: Optional[float] = None):
        """Block until a client -> server message is queued and return it (network
        thread). One accessor for every kind, since they are all sent the same way."""
        return self._outgoing.get(timeout=timeout)

    def latest(self) -> Optional[GameSnapshot]:
        """The game as of now, or ``None`` before the first full snapshot arrives.

        Rebuilt on each call rather than stored, because "now" moves between calls: the
        render loop asks once a frame, and that is what walks a piece across the board
        between the two messages that announce its departure and its arrival.
        """
        with self._lock:
            return self._state.current()

    @property
    def color(self) -> Optional[Color]:
        """The colour the server assigned this client, or ``None`` if not a player."""
        with self._lock:
            return self._color

    @property
    def rating(self) -> Optional[int]:
        """This client's ELO rating from its Welcome, or ``None`` before logging in."""
        with self._lock:
            return self._rating

    @property
    def room_id(self) -> Optional[str]:
        """The private room's id if seated via a room, else ``None`` (matchmade game)."""
        with self._lock:
            return self._room_id

    def take_rejection(self) -> Optional[str]:
        """The last rejection reason, cleared on read so the UI shows it only once."""
        with self._lock:
            reason = self._rejection
            self._rejection = None
            return reason

    def start(self, url: str) -> None:  # pragma: no cover  (spawns the network thread)
        """Connect on a background daemon thread; returns immediately."""
        thread = threading.Thread(target=self._run, args=(url,), daemon=True)
        thread.start()

    def _run(self, url: str) -> None:  # pragma: no cover  (asyncio entry on the thread)
        import asyncio

        asyncio.run(self._connect(url))

    async def _connect(self, url: str) -> None:  # pragma: no cover  (WebSocket recv/send)
        import asyncio

        import websockets

        from kfchess.shared.protocol import encode

        async with websockets.connect(url) as websocket:
            loop = asyncio.get_event_loop()

            async def receive() -> None:
                async for text in websocket:
                    self.handle(text)

            async def transmit() -> None:
                # Every outbound kind rides one queue, so one sender drains them all in
                # the order they were queued.
                while True:
                    message = await loop.run_in_executor(None, self.next_outgoing)
                    await websocket.send(encode(message))

            await asyncio.gather(receive(), transmit())
