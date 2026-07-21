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
    Event,
    Login,
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

        Also flushes any events queued since the session was built straight to this
        client (in practice, just the initial "game started" — so each player hears the
        start sound the moment their own window connects, not before anyone was there
        to hear it).
        """
        client_id = self._next_id
        self._next_id += 1
        self._sends[client_id] = send
        color = self._session.assign_color()
        if color is not None:
            self._colors[client_id] = color
            send(encode(Assigned(color)))
        send(encode(State(self._session.snapshot())))
        for kind in self._session.drain_events():
            send(encode(Event(kind)))
        return client_id

    def receive(self, client_id: int, text: str) -> None:
        """Handle one wire message from a client. Unrecognised messages are ignored."""
        try:
            message = decode(text)
        except ValueError:
            return  # not valid JSON, or an unknown message type — drop it
        if isinstance(message, Login):
            self._on_login(client_id, message.username)
            return
        if not isinstance(message, Move):
            return  # nothing else comes from a client
        color = self._colors.get(client_id)
        if color is None:
            self._send_to(client_id, Rejected("not_a_player"))
            return
        reason = self._session.apply_command(color, message.cmd)
        if reason is not None:
            self._send_to(client_id, Rejected(reason))
        else:
            self.broadcast_events()
            self.broadcast_state()

    def _on_login(self, client_id: int, username: str) -> None:
        """Record ``username`` for whichever colour ``client_id`` plays, if any.

        A spectator (no assigned colour) has nowhere for a name to show yet, so its
        Login is silently ignored — spectator identity arrives with rooms in M6. The
        name is part of the game's *state* (like score), so it goes out on the next
        state broadcast rather than the immediate-event channel.
        """
        color = self._colors.get(client_id)
        if color is None:
            return
        self._session.set_name(color, username)
        self.broadcast_state()

    def disconnect(self, client_id: int) -> None:
        """Forget a client that has left."""
        self._sends.pop(client_id, None)
        self._colors.pop(client_id, None)

    def tick(self, dt_ms: int) -> None:
        """Advance the game by ``dt_ms`` and broadcast the new state to everyone."""
        self._session.tick(dt_ms)
        self.broadcast_events()
        self.broadcast_state()

    def broadcast_state(self) -> None:
        """Send the current snapshot to every connected client."""
        text = encode(State(self._session.snapshot()))
        for send in self._sends.values():
            send(text)

    def broadcast_events(self) -> None:
        """Send every sound-kind event queued since the last drain to all clients.

        Sent *alongside* the state broadcast, not instead of it — the board's truth
        always comes from the snapshot; this is only a one-shot nudge ("play this
        sound now") for whichever client has a local player wired to react to it.

        With no clients connected, this deliberately does *not* drain the session's
        queue: the background ticker calls this every tick regardless of connections,
        and draining with nobody to send to would silently discard the event (in
        particular, the initial "game started" event, queued before anyone has
        connected) instead of leaving it for the next :meth:`connect` to deliver.
        """
        if not self._sends:
            return
        for kind in self._session.drain_events():
            text = encode(Event(kind))
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
