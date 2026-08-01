"""The shard: it owns the games, and it has never seen a socket.

This is what is left of the server once the sockets move out. It subscribes to what the
gateways report, drives the same :class:`~kfchess.server.lobby.Lobby` that ran the whole
server before, and publishes the answers back onto the bus. The lobby's dispatch — who
may log in, who is matched with whom, which moves are legal, who is a spectator — is
untouched; all that changed is where its messages arrive from and where they go.

Two translations happen here and nowhere else:

- **A connection becomes a client.** A gateway names its sockets (``gw1.7``); the lobby
  numbers its clients. The shard keeps the map, so neither has to know the other's
  vocabulary, and a reply is addressed by prefixing ``conn.`` to a string it never takes
  apart.
- **A seat becomes a subscription.** When the lobby puts a connection in a game, the next
  message to that connection carries the room for its gateway to follow. The gateway is
  *told*; it never infers a room by reading a ``Seated``, which is what keeps it unable to
  understand the game at all.

Everything below :meth:`Shard.tick` is synchronous and driven by calling it, so a test
wires a gateway to a shard through :class:`~kfchess.bus.message_bus.InProcessMessageBus` and
plays a whole game in one thread. :func:`serve` is the irreducible async shell.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

from kfchess.bus import subjects
from kfchess.bus.envelope import (
    ClientEventKind,
    ToClient,
    decode_client_event,
    encode,
)
from kfchess.server.lobby import Lobby, NewBoard
from kfchess.services.shared import SharedState
from kfchess.server.user_store import UserStore

_log = logging.getLogger(__name__)  # silent until configure_logging runs


class Shard:
    """One game server process: a lobby, plus its two ends of the message bus."""

    def __init__(
        self,
        bus,
        new_board: NewBoard,
        users: UserStore,
        shared: Optional[SharedState] = None,
    ) -> None:
        self._bus = bus
        self._hub = Lobby(new_board, users, shared, to_room=self._publish)
        # conn_id -> the lobby's own client number, and the room that connection has
        # already been told to follow. Both are dropped when the socket closes.
        self._client_of: Dict[str, int] = {}
        self._following: Dict[str, int] = {}
        self._bus.subscribe(subjects.LOBBY_CMD, self._on_client_event)

    # --- what the gateways report ---------------------------------------------

    def _on_client_event(self, subject: str, payload: str) -> None:
        """One thing that happened on one socket, somewhere out there."""
        event = decode_client_event(payload)
        if event.kind is ClientEventKind.CONNECTED:
            self._client_of[event.conn_id] = self._hub.connect(self._sender(event.conn_id))
            _log.info("connection %s registered", event.conn_id)
        elif event.kind is ClientEventKind.MESSAGE:
            client_id = self._client_of.get(event.conn_id)
            if client_id is not None:  # it closed before this arrived
                self._hub.receive(client_id, event.text)
        else:
            self._on_gone(event.conn_id)

    def _on_gone(self, conn_id: str) -> None:
        """A socket closed. Whether that matters is the lobby's to decide: a player
        dropping starts a resign countdown, a spectator leaving is nothing at all."""
        self._following.pop(conn_id, None)
        client_id = self._client_of.pop(conn_id, None)
        if client_id is not None:
            self._hub.disconnect(client_id)
            _log.info("connection %s gone", conn_id)

    # --- what the shard answers -----------------------------------------------

    def _sender(self, conn_id: str):
        """The lobby's ``send`` for one connection: publish to that connection's mailbox."""

        def send(text: str) -> None:
            self._bus.publish(
                subjects.connection(conn_id),
                encode(ToClient(text, self._room_to_follow(conn_id))),
            )

        return send

    def _room_to_follow(self, conn_id: str) -> Optional[str]:
        """The room this connection has just been put in and not yet been told about.

        Answered once per game: the first message after a seat carries it, everything
        after rides the subscription that opened. A reconnect into the same game answers
        again, because the gateway holding the socket is a different one — or at least
        the shard is not entitled to assume it is not.
        """
        game_id = self._hub.game_of(self._client_of.get(conn_id, -1))
        if game_id is None or self._following.get(conn_id) == game_id:
            return None
        self._following[conn_id] = game_id
        return str(game_id)

    def _publish(self, subject: str, text: str) -> None:
        """The lobby's room sink: one publish for a whole room, whoever is in it."""
        self._bus.publish(subject, text)

    # --- time ------------------------------------------------------------------

    def tick(self, dt_ms: int) -> None:
        """Advance every game this shard is running."""
        self._hub.tick(dt_ms)

    def next_event_delay_ms(self) -> Optional[int]:
        """When this shard next has something to do — see :func:`next_sleep_s`."""
        return self._hub.next_event_delay_ms()


def next_sleep_s(shard, ceiling_ms: int) -> float:
    """How long the ticker may sleep before the shard needs attention again.

    Until the soonest moment any game has scheduled — a piece arriving, a cooldown
    ending, a resign countdown reaching zero — but never longer than ``ceiling_ms``.

    The ceiling is what keeps the *periodic* duties on their own clock: the ten-second
    resync and the matchmaking timeouts count elapsed time rather than name a moment, so
    they need the loop to come round regularly whether or not a game has anything to do.
    Within that, this only ever pulls a wake-up *earlier*: a piece due in 10 ms is
    announced in 10 ms, instead of at whatever fixed boundary comes next.
    """
    due_ms = shard.next_event_delay_ms()
    return (ceiling_ms if due_ms is None else min(due_ms, ceiling_ms)) / 1000


async def run_games(shard: Shard, tick_ms: int = None) -> None:  # pragma: no cover
    """Advance ``shard``'s games for ever, waking only when one of them needs it.

    The clock, and nothing else. Both deployments run this exact loop — a shard on the
    far end of NATS, and the solo server in the same process as its own sockets — so
    time passes the same way in a game played on a laptop and one played on a cluster.
    """
    import asyncio
    import time

    from kfchess.config import SERVER_TICK_MS

    tick_ms = tick_ms or SERVER_TICK_MS
    # Measured elapsed time, not the interval we asked to sleep for: a loop that advances
    # by a constant falls further behind the wall clock the busier it gets.
    last = time.monotonic()
    while True:
        await asyncio.sleep(next_sleep_s(shard, tick_ms))
        now = time.monotonic()
        shard.tick(round((now - last) * 1000))
        last = now


async def serve(  # pragma: no cover  (irreducible async NATS + timer I/O)
    new_board: NewBoard,
    nats_url: str = None,
    tick_ms: int = None,
) -> None:
    """Run one shard until cancelled: answer the bus, and advance the games.

    No ``websockets`` import anywhere in this file — that is the point of the stage. The
    two things it decides, how long to sleep and how much time has passed, are
    :func:`next_sleep_s` and a subtraction; everything else is in :class:`Shard`.

    This is the deployment where the shared state has to be genuinely shared, so it opens
    a Redis. The solo server builds the same :class:`~kfchess.services.shared.SharedState`
    over a dictionary and runs the same lobby against it.
    """
    import asyncio

    from kfchess.bus.message_bus import connect
    from kfchess.config import NATS_URL, REDIS_URL, SHARD_ID
    from kfchess.services.shared import SharedState
    from kfchess.services.store import connect as connect_store

    bus = await connect(nats_url or NATS_URL)
    shared = SharedState.on(connect_store(REDIS_URL), SHARD_ID)
    shard = Shard(bus, new_board, UserStore(), shared)

    await asyncio.gather(bus.run(), run_games(shard, tick_ms))
