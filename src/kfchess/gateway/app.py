"""The gateway: a socket on one side, a subject on the other, and nothing in between.

:class:`Gateway` is the whole of it, and it is synchronous — it is handed a message bus
and a ``send`` callable per connection, so a test can open a connection, feed it a string,
and read what reached the bus, with no sockets and no event loop. :func:`serve` is the
irreducible part: real WebSockets, a real NATS connection, excluded from coverage exactly
like ``shard.serve`` and the cv2 calls in ``img.py``.

What the gateway knows is deliberately almost nothing:

- A socket opened, said something, or closed. It reports each as a
  :class:`~kfchess.bus.envelope.ClientEvent` on ``lobby.cmd`` and never looks inside the
  text.
- A message arrived for one of its connections. It forwards the text, and if the envelope
  says to follow a room, it follows it.
- A message arrived for a room it follows. It forwards the text to every connection here
  in that room.

That is the entire vocabulary. It cannot tell a move from a resignation, a player from a
spectator, or a won game from a lost one — and a spectator needs no special case anywhere
in this file, because "watching" *is* the ordinary case: a connection in a room, receiving
what that room broadcasts. The one asymmetry — that a watcher's moves are refused — is the
shard's to enforce, and it comes back as an ordinary reply on that connection's mailbox.
"""

from __future__ import annotations

import logging

from kfchess.bus import subjects
from kfchess.bus.envelope import (
    ClientEvent,
    ClientEventKind,
    decode_to_client,
    encode,
)
from kfchess.gateway.router import ConnectionRouter, Send

_log = logging.getLogger(__name__)  # silent until configure_logging runs


class Gateway:
    """Moves text between sockets and subjects, and holds no game state at all."""

    def __init__(self, bus, gateway_id: str) -> None:
        self._bus = bus
        self._gateway_id = gateway_id
        self._router = ConnectionRouter(gateway_id)
        # Every reply addressed to any connection this gateway holds. One subscription
        # for the whole gateway, not one per socket.
        self._bus.subscribe(subjects.gateway_inbox(gateway_id), self._on_reply)

    # --- sockets -> the bus ---------------------------------------------------

    def connect(self, send: Send) -> str:
        """Register an open socket and tell the shard it exists."""
        conn_id = self._router.open(send)
        _log.info("connection %s opened", conn_id)
        self._report(ClientEventKind.CONNECTED, conn_id)
        return conn_id

    def receive(self, conn_id: str, text: str) -> None:
        """Forward what a client said, verbatim and unread."""
        self._report(ClientEventKind.MESSAGE, conn_id, text)

    def disconnect(self, conn_id: str) -> None:
        """Forget a socket, drop any room nobody here is left watching, and say so.

        The shard is told last, and told regardless: it is what decides whether this
        mattered — a player dropping starts a resign countdown, a spectator leaving is
        nothing at all — and that is a decision this side is not entitled to make.
        """
        for room in self._router.close(conn_id):
            self._bus.unsubscribe(subjects.room_inbox(room))
            _log.info("no longer following room %s", room)
        _log.info("connection %s closed", conn_id)
        self._report(ClientEventKind.DISCONNECTED, conn_id)

    def _report(self, kind: ClientEventKind, conn_id: str, text: str = "") -> None:
        self._bus.publish(subjects.LOBBY_CMD, encode(ClientEvent(kind, conn_id, text)))

    # --- the bus -> sockets ---------------------------------------------------

    def _on_reply(self, subject: str, payload: str) -> None:
        """A message for one of this gateway's connections."""
        conn_id = subjects.connection_of(subject)
        reply = decode_to_client(payload)
        if reply.follow_room is not None:
            self._follow(conn_id, reply.follow_room)
        send = self._router.to_connection(conn_id)
        if send is not None:  # it may have closed while the answer was in flight
            send(reply.text)

    def _follow(self, conn_id: str, room: str) -> None:
        """Start following a room's broadcasts, if nobody here is following it yet."""
        if self._router.follow(conn_id, room):
            self._bus.subscribe(subjects.room_inbox(room), self._on_broadcast)
            _log.info("following room %s", room)

    def _on_broadcast(self, subject: str, payload: str) -> None:
        """A message for a whole room: hand it to everyone here who is in it.

        One copy crossed the network however many people are in the room; this is where
        it becomes one copy per socket, on the machine that already holds them.
        """
        room = subjects.room_of(subject)
        for send in self._router.in_room(room):
            send(payload)

    @property
    def connections(self) -> int:
        """How many sockets this gateway is holding."""
        return len(self._router)


async def serve(  # pragma: no cover  (irreducible async socket + NATS I/O)
    gateway_id: str,
    host: str = None,
    port: int = None,
    nats_url: str = None,
) -> None:
    """Accept WebSockets and bridge them onto NATS until cancelled.

    Every decision this makes is in :class:`Gateway` above and is tested there; what is
    left is opening a listener, opening a NATS connection, and pumping bytes between the
    two — the same thin shell ``shard.serve`` is.
    """
    import asyncio

    import websockets

    from kfchess.bus.message_bus import connect
    from kfchess.config import (
        NATS_URL,
        SERVER_HOST,
        SERVER_PORT,
        WS_PING_INTERVAL_S,
        WS_PING_TIMEOUT_S,
    )

    host = host or SERVER_HOST
    port = port or SERVER_PORT
    bus = await connect(nats_url or NATS_URL)
    gateway = Gateway(bus, gateway_id)

    async def drain(queue: "asyncio.Queue", websocket) -> None:
        while True:
            await websocket.send(await queue.get())

    async def handler(websocket) -> None:
        queue: "asyncio.Queue" = asyncio.Queue()
        conn_id = gateway.connect(queue.put_nowait)
        sender = asyncio.create_task(drain(queue, websocket))
        try:
            async for text in websocket:
                gateway.receive(conn_id, text)
        finally:
            gateway.disconnect(conn_id)
            sender.cancel()

    async with websockets.serve(
        handler,
        host,
        port,
        ping_interval=WS_PING_INTERVAL_S,
        ping_timeout=WS_PING_TIMEOUT_S,
    ):
        await bus.run()  # forever: performs the queued publishes and subscriptions
