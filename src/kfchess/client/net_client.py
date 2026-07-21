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
from typing import Optional

from kfchess.model.color import Color
from kfchess.protocol import Assigned, Event, Rejected, State, decode
from kfchess.snapshot import GameSnapshot


class NetClient:
    """Thread-safe bridge between the cv2 main loop and the background WebSocket."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snapshot: Optional[GameSnapshot] = None
        self._color: Optional[Color] = None
        self._rejection: Optional[str] = None
        self._outgoing: "queue.Queue[str]" = queue.Queue()
        # One-shot perception events (sound kinds) queued separately from the
        # snapshot/colour/rejection state above: each is consumed exactly once by
        # next_event(), not just "the latest value", since every one matters.
        self._events: "queue.Queue[str]" = queue.Queue()

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
            elif isinstance(message, Assigned):
                self._color = message.color
            elif isinstance(message, Rejected):
                self._rejection = message.reason
            elif isinstance(message, Event):
                self._events.put(message.kind)

    def queue_command(self, cmd: str) -> None:
        """Queue a move command (e.g. ``"WQe2e5"``) for the network thread to send."""
        self._outgoing.put(cmd)

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

        from kfchess.protocol import Move, encode

        async with websockets.connect(url) as websocket:

            async def receive() -> None:
                async for text in websocket:
                    self.handle(text)

            async def transmit() -> None:
                loop = asyncio.get_event_loop()
                while True:
                    cmd = await loop.run_in_executor(None, self._outgoing.get)
                    await websocket.send(encode(Move(cmd)))

            await asyncio.gather(receive(), transmit())
