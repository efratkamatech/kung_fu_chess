"""NetClient: the client's network half — connect, send commands, receive snapshots.

The windowed client's cv2 loop runs on the main thread and must never block on the
network, so the socket lives on a background thread with its own asyncio loop. This
class is the bridge between the two threads: the background thread pushes decoded state
*in* (:meth:`handle`), and the main thread reads the latest snapshot *out*
(:meth:`latest` / :attr:`color`) and queues commands to send
(:meth:`queue_command`) — all guarded by a lock so the two threads never corrupt shared
state.

The decode/store/read logic is synchronous and unit-tested. The thread, the asyncio
loop, and the WebSocket recv/send are the irreducible I/O and are excluded from
coverage, like the cv2 calls in ``img.py``.
"""

from __future__ import annotations

import queue
import threading
from typing import Optional, Tuple

from kfchess.model.color import Color
from kfchess.protocol import (
    CreateRoom,
    Event,
    JoinRoom,
    Notice,
    Rejected,
    Seated,
    State,
    Welcome,
    decode,
)
from kfchess.snapshot import GameSnapshot

Credentials = Tuple[str, str]  # (username, password)
# The answer to a "Play" request: ("seated", colour) once matched, or
# ("notice", reason) — e.g. ("notice", "no_opponent") — if the search timed out.
MatchResult = Tuple[str, object]


class NetClient:
    """Thread-safe bridge between the cv2 main loop and the background WebSocket."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snapshot: Optional[GameSnapshot] = None
        self._color: Optional[Color] = None
        self._rating: Optional[int] = None
        self._room_id: Optional[str] = None
        self._logged_in = False
        self._rejection: Optional[str] = None
        self._outgoing: "queue.Queue[str]" = queue.Queue()
        # One-shot perception events (sound kinds) queued separately from the
        # snapshot/colour/rejection state above: each is consumed exactly once by
        # next_event(), not just "the latest value", since every one matters.
        self._events: "queue.Queue[str]" = queue.Queue()
        # Credentials waiting to be sent as Login messages (one per login attempt).
        self._login_queue: "queue.Queue[Credentials]" = queue.Queue()
        # The outcome of each login attempt: None = accepted, else the refusal reason.
        self._login_results: "queue.Queue[Optional[str]]" = queue.Queue()
        # "Play" requests waiting to be sent, and the answer to each (seated / notice).
        self._play_queue: "queue.Queue[None]" = queue.Queue()
        self._match_results: "queue.Queue[MatchResult]" = queue.Queue()
        # Room actions waiting to be sent (a CreateRoom or JoinRoom message object).
        self._room_queue: "queue.Queue" = queue.Queue()

    def handle(self, text: str) -> None:
        """Process one incoming wire message: store the snapshot, colour, or rejection.

        Called from the network thread. Garbage or unexpected messages are dropped.
        """
        try:
            message = decode(text)
        except ValueError:
            return
        with self._lock:
            if isinstance(message, State):
                self._snapshot = message.snapshot
            elif isinstance(message, Welcome):
                self._color = message.color
                self._rating = message.rating
                self._logged_in = True
                self._login_results.put(None)  # login accepted
            elif isinstance(message, Seated):
                self._color = message.color  # put in a game as this colour (None = watcher)
                self._room_id = message.room_id  # set when seated via a room
                self._match_results.put(("seated", message.color))
            elif isinstance(message, Notice):
                # A lobby notice (e.g. "no_opponent") answers a pending Play request.
                self._match_results.put(("notice", message.reason))
            elif isinstance(message, Rejected):
                # Before logging in, a rejection means the login was refused (bad
                # password); after, it means a move was refused.
                if self._logged_in:
                    self._rejection = message.reason
                else:
                    self._login_results.put(message.reason)
            elif isinstance(message, Event):
                self._events.put(message.kind)

    def queue_command(self, cmd: str) -> None:
        """Queue a move command (e.g. ``"WQe2e5"``) for the network thread to send."""
        self._outgoing.put(cmd)

    def login(self, username: str, password: str) -> None:
        """Queue a login attempt; the network thread sends it as a Login message.

        May be called more than once (retry after a bad password) — each attempt's
        outcome is reported by one :meth:`wait_for_login`.
        """
        self._login_queue.put((username, password))

    def wait_for_login(self, timeout: Optional[float] = None) -> Optional[str]:
        """Block until the server answers a login attempt.

        Returns ``None`` if it was accepted, or the refusal reason (e.g.
        ``"bad_password"``) if not — the caller can then prompt again and retry.
        """
        return self._login_results.get(timeout=timeout)

    def next_login(self, timeout: Optional[float] = None) -> Credentials:
        """Block until a login attempt is queued and return it (network thread)."""
        return self._login_queue.get(timeout=timeout)

    def play(self) -> None:
        """Queue a "Play" request; the network thread sends it as a Play message.

        The answer (matched, or no opponent) is reported by one :meth:`wait_for_match`.
        """
        self._play_queue.put(None)

    def next_play(self, timeout: Optional[float] = None) -> None:
        """Block until a "Play" request is queued (network thread); returns nothing."""
        return self._play_queue.get(timeout=timeout)

    def wait_for_match(self, timeout: Optional[float] = None) -> MatchResult:
        """Block until the server answers a "Play", "create room", or "join room" request.

        Returns ``("seated", colour)`` once placed in a game (``colour`` is ``None`` for
        a spectator), or ``("notice", reason)`` — e.g. ``"no_opponent"`` or
        ``"no_such_room"`` — so the caller can prompt the player to try again.
        """
        return self._match_results.get(timeout=timeout)

    def create_room(self) -> None:
        """Queue a "create room" request; the answer comes via :meth:`wait_for_match`."""
        self._room_queue.put(CreateRoom())

    def join_room(self, room_id: str) -> None:
        """Queue a "join room" request; the answer comes via :meth:`wait_for_match`."""
        self._room_queue.put(JoinRoom(room_id))

    def next_room_action(self, timeout: Optional[float] = None):
        """Block until a room action is queued and return it (network thread)."""
        return self._room_queue.get(timeout=timeout)

    def next_event(self) -> Optional[str]:
        """The next queued sound-kind event (e.g. ``"capture"``), or ``None`` if none
        are waiting. Called once per frame by the render loop to drain the queue."""
        try:
            return self._events.get_nowait()
        except queue.Empty:
            return None

    def next_command(self, timeout: Optional[float] = None) -> str:
        """Block until a queued command is available and return it (network thread)."""
        return self._outgoing.get(timeout=timeout)

    def latest(self) -> Optional[GameSnapshot]:
        """The most recent snapshot received, or ``None`` before the first arrives."""
        with self._lock:
            return self._snapshot

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

        from kfchess.protocol import Login, Move, Play, encode

        async with websockets.connect(url) as websocket:
            loop = asyncio.get_event_loop()

            async def receive() -> None:
                async for text in websocket:
                    self.handle(text)

            async def send_logins() -> None:
                while True:
                    username, password = await loop.run_in_executor(None, self.next_login)
                    await websocket.send(encode(Login(username, password)))

            async def send_plays() -> None:
                while True:
                    await loop.run_in_executor(None, self.next_play)
                    await websocket.send(encode(Play()))

            async def send_rooms() -> None:
                while True:
                    action = await loop.run_in_executor(None, self.next_room_action)
                    await websocket.send(encode(action))

            async def transmit() -> None:
                while True:
                    cmd = await loop.run_in_executor(None, self._outgoing.get)
                    await websocket.send(encode(Move(cmd)))

            await asyncio.gather(
                receive(), send_logins(), send_plays(), send_rooms(), transmit()
            )
