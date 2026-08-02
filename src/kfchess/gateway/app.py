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
from kfchess.bus.message_bus import MessageBus
from kfchess.bus.envelope import (
    ClientEvent,
    ClientEventKind,
    decode_to_client,
    encode,
)
from kfchess.gateway.router import ConnectionRouter, Send
from kfchess.obs.measures import BYTES_OUT, CONNECTIONS

_log = logging.getLogger(__name__)  # silent until configure_logging runs


class Gateway:
    """Moves text between sockets and subjects, and holds no game state at all."""

    def __init__(self, bus: MessageBus, gateway_id: str) -> None:
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
        CONNECTIONS.set(len(self._router))
        _log.info("connection %s opened", conn_id)
        self._report(ClientEventKind.CONNECTED, conn_id)
        return conn_id

    def receive(self, conn_id: str, text: str) -> None:
        """Forward what a client said, verbatim and unread, to whoever owns her.

        Held instead if nobody owns her yet — the socket has only just opened and the
        claim is still in flight. Answering her first two messages from two different
        shards would be worse than a moment's delay: the second one would not know who
        she is.
        """
        owner = self._router.owner(conn_id)
        if owner is None:
            self._router.hold(conn_id, text)
            return
        self._send_to_shard(owner, ClientEventKind.MESSAGE, conn_id, text)

    def disconnect(self, conn_id: str) -> None:
        """Forget a socket, drop any room nobody here is left watching, and say so.

        The shard is told last, and told regardless: it is what decides whether this
        mattered — a player dropping starts a resign countdown, a spectator leaving is
        nothing at all — and that is a decision this side is not entitled to make.
        """
        owner = self._router.owner(conn_id)
        for room in self._router.close(conn_id):
            self._bus.unsubscribe(subjects.room_inbox(room))
            _log.info("no longer following room %s", room)
        CONNECTIONS.set(len(self._router))
        _log.info("connection %s closed", conn_id)
        if owner is None:
            self._report(ClientEventKind.DISCONNECTED, conn_id)  # nobody claimed her
        else:
            self._send_to_shard(owner, ClientEventKind.DISCONNECTED, conn_id)

    def _report(self, kind: ClientEventKind, conn_id: str, text: str = "") -> None:
        """Announce a connection nobody owns. Exactly one shard will pick it up."""
        self._bus.publish(subjects.LOBBY_CMD, encode(ClientEvent(kind, conn_id, text)))

    def _send_to_shard(
        self, shard_id: str, kind: ClientEventKind, conn_id: str, text: str = ""
    ) -> None:
        """Send to the shard that owns this connection, by name."""
        self._bus.publish(
            subjects.shard_cmd(shard_id), encode(ClientEvent(kind, conn_id, text))
        )

    # --- the bus -> sockets ---------------------------------------------------

    def _on_reply(self, subject: str, payload: str) -> None:
        """A message for one of this gateway's connections, and what to do about it."""
        conn_id = subjects.connection_of(subject)
        reply = decode_to_client(payload)
        if reply.claim is not None:
            self._claim(conn_id, reply.claim)
        if reply.follow_room is not None:
            self._follow(conn_id, reply.follow_room)
        send = self._router.to_connection(conn_id)
        if send is not None and reply.text:  # it may have closed; and a claim carries no text
            BYTES_OUT.inc(len(reply.text))
            send(reply.text)

    def _claim(self, conn_id: str, shard_id: str) -> None:
        """Note who owns this connection now, and forward whatever was said meanwhile."""
        held = self._router.claim(conn_id, shard_id)
        _log.info("connection %s belongs to %s", conn_id, shard_id)
        for text in held:
            self._send_to_shard(shard_id, ClientEventKind.MESSAGE, conn_id, text)

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
            # Counted here, per socket, because here is where one message crossing the
            # network becomes one copy per player -- which is the number the design's
            # bytes-per-connection claim is about.
            BYTES_OUT.inc(len(payload))
            send(payload)

    @property
    def connections(self) -> int:
        """How many sockets this gateway is holding."""
        return len(self._router)


async def listen(  # pragma: no cover  (irreducible async socket I/O)
    gateway: Gateway,
    host: str = None,
    port: int = None,
):
    """Open the WebSocket listener that feeds ``gateway``, and hand it back.

    An async context manager, so the caller decides what to run *while* it is open —
    :func:`serve` runs the NATS pump, and the solo server runs the games themselves.
    That is the only difference between the two deployments on this side of the wire:
    the sockets, the connection ids, and every decision in :class:`Gateway` are the same
    in both, which is what makes "it works locally" evidence about the other one.
    """
    import asyncio

    import websockets

    from kfchess.config import (
        SERVER_HOST,
        SERVER_PORT,
        WS_PING_INTERVAL_S,
        WS_PING_TIMEOUT_S,
    )

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

    return websockets.serve(
        handler,
        host or SERVER_HOST,
        port or SERVER_PORT,
        ping_interval=WS_PING_INTERVAL_S,
        ping_timeout=WS_PING_TIMEOUT_S,
    )


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
    from kfchess.bus.message_bus import connect
    from kfchess.config import NATS_URL, OBS_PORT
    from kfchess.obs.endpoint import serve_observability

    serve_observability(OBS_PORT)
    bus = await connect(nats_url or NATS_URL)
    async with await listen(Gateway(bus, gateway_id), host, port):
        await bus.run()  # forever: performs the queued publishes and subscriptions
