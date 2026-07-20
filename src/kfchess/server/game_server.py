"""The WebSocket game server: a testable sync hub plus a thin async I/O wrapper.

Two layers, split so the logic can be fully tested without any sockets:

- :class:`GameServer` — a *synchronous* hub. It owns one :class:`GameSession` and the
  set of connected clients, each represented only by a ``send(text)`` callback. All the
  behaviour lives here: assign a colour on connect, decode and apply moves, broadcast
  state, reject bad moves, drop clients. Every branch is unit-tested with fake clients.
- :func:`serve` — the irreducible async part: it accepts real WebSocket connections,
  pumps outgoing messages through a per-connection queue, and ticks the game on a timer.
  It only wires sockets to the hub, so it is excluded from coverage like the cv2 I/O in
  ``img.py``.
"""

from __future__ import annotations

from typing import Callable, Dict, Optional

from kfchess.model.color import Color
from kfchess.protocol import (
    Assigned,
    Move,
    Rejected,
    State,
    decode,
    encode,
)
from kfchess.server.session import GameSession

Send = Callable[[str], None]  # how the hub pushes one wire string to one client


class GameServer:
    """A synchronous hub over one :class:`GameSession`; clients are ``send`` callbacks."""

    def __init__(self, session: GameSession) -> None:
        self._session = session
        self._sends: Dict[int, Send] = {}       # client id -> its send callback
        self._colors: Dict[int, Color] = {}     # client id -> its colour (players only)
        self._next_id = 0

    def connect(self, send: Send) -> int:
        """Register a new client. Assign a colour if free, then send it the state.

        Returns the client id used by :meth:`receive` and :meth:`disconnect`. A third
        client gets no colour (it can watch but not move — spectators arrive in M6).
        """
        client_id = self._next_id
        self._next_id += 1
        self._sends[client_id] = send
        color = self._session.assign_color()
        if color is not None:
            self._colors[client_id] = color
            send(encode(Assigned(color)))
        send(encode(State(self._session.snapshot())))
        return client_id

    def receive(self, client_id: int, text: str) -> None:
        """Handle one wire message from a client. Non-moves and garbage are ignored."""
        try:
            message = decode(text)
        except ValueError:
            return  # not valid JSON, or an unknown message type — drop it
        if not isinstance(message, Move):
            return  # only move commands come from clients in M2
        color = self._colors.get(client_id)
        if color is None:
            self._send_to(client_id, Rejected("not_a_player"))
            return
        reason = self._session.apply_command(color, message.cmd)
        if reason is not None:
            self._send_to(client_id, Rejected(reason))
        else:
            self.broadcast_state()

    def disconnect(self, client_id: int) -> None:
        """Forget a client that has left."""
        self._sends.pop(client_id, None)
        self._colors.pop(client_id, None)

    def tick(self, dt_ms: int) -> None:
        """Advance the game by ``dt_ms`` and broadcast the new state to everyone."""
        self._session.tick(dt_ms)
        self.broadcast_state()

    def broadcast_state(self) -> None:
        """Send the current snapshot to every connected client."""
        text = encode(State(self._session.snapshot()))
        for send in self._sends.values():
            send(text)

    def _send_to(self, client_id: int, message) -> None:
        send = self._sends.get(client_id)
        if send is not None:
            send(encode(message))


async def serve(  # pragma: no cover  (irreducible async socket + timer I/O)
    board,
    host: Optional[str] = None,
    port: Optional[int] = None,
    tick_ms: Optional[int] = None,
) -> None:
    """Run the WebSocket server until cancelled, driving one :class:`GameServer`.

    Each connection gets an outgoing asyncio queue that a drain task feeds to the
    socket, so the synchronous hub can "send" by simply enqueuing. A background ticker
    advances the game and broadcasts on a fixed interval. This is pure socket/timer
    plumbing around the tested hub, hence excluded from coverage.
    """
    import asyncio

    import websockets

    from kfchess.config import SERVER_HOST, SERVER_PORT, SERVER_TICK_MS

    host = host or SERVER_HOST
    port = port or SERVER_PORT
    tick_ms = tick_ms or SERVER_TICK_MS
    hub = GameServer(GameSession(board))

    async def drain(queue: "asyncio.Queue", websocket) -> None:
        while True:
            await websocket.send(await queue.get())

    async def handler(websocket) -> None:
        queue: "asyncio.Queue" = asyncio.Queue()
        client_id = hub.connect(queue.put_nowait)
        sender = asyncio.create_task(drain(queue, websocket))
        try:
            async for text in websocket:
                hub.receive(client_id, text)
        finally:
            hub.disconnect(client_id)
            sender.cancel()

    async def ticker() -> None:
        while True:
            await asyncio.sleep(tick_ms / 1000)
            hub.tick(tick_ms)

    async with websockets.serve(handler, host, port):
        await ticker()
