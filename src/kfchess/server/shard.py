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
from typing import Dict, Optional, Set, Tuple

from kfchess.bus import subjects
from kfchess.bus.message_bus import MessageBus
from kfchess.config import SHARD_HEARTBEAT_MS
from kfchess.bus.envelope import (
    ClientEventKind,
    Seatee,
    ToClient,
    decode_auth_result,
    decode_client_event,
    decode_join_game,
    decode_start_game,
    encode,
)
from kfchess.obs.measures import ACTIVE_GAMES, CLIENTS
from kfchess.server.lobby import Lobby, NewBoard
from kfchess.services.shared import SharedState
from kfchess.server.user_store import UserStore

_log = logging.getLogger(__name__)  # silent until configure_logging runs


class Shard:
    """One game server process: a lobby, plus its two ends of the message bus."""

    def __init__(
        self,
        bus: MessageBus,
        new_board: NewBoard,
        users: UserStore,
        shared: Optional[SharedState] = None,
    ) -> None:
        self._bus = bus
        shared = shared if shared is not None else SharedState.on()
        self._shard_id = shared.shard_id
        self._allocator = shared.allocator
        # Time since this shard last said it was alive. It says so immediately, so that a
        # shard which has only just started can be given a game before its first tick.
        self._since_heartbeat_ms = 0
        self._allocator.announce(self._shard_id, 0)
        self._hub = Lobby(
            new_board,
            users,
            shared,
            to_room=self._publish,
            to_shard=self._publish,
            to_auth=self._publish,
        )
        # conn_id -> the lobby's own client number, and the room that connection has
        # already been told to follow. Both are dropped when the socket closes.
        self._client_of: Dict[str, int] = {}
        self._following: Dict[str, int] = {}
        # The connections this shard has told a gateway are its own. A connection is in
        # here at most once; the entry is what stops every later answer repeating a claim
        # the gateway acted on long ago.
        self._claimed: Set[str] = set()
        # A socket nobody owns yet, announced to every shard at once. The queue group is
        # what makes "every shard" mean "exactly one of them" -- without it, two shards
        # would each claim the same connection and each run its own copy of her game.
        self._bus.subscribe(
            subjects.LOBBY_CMD, self._on_client_event, queue_group=subjects.SHARD_GROUP
        )
        # And everything from the connections this shard already owns, addressed to it
        # by name. No group here: these are nobody else's to answer.
        self._bus.subscribe(subjects.shard_cmd(self._shard_id), self._on_client_event)
        # And games handed to this shard by another one that made the match.
        self._bus.subscribe(
            subjects.shard_start_game(self._shard_id), self._on_start_game
        )
        # ...and players sent here because the room they typed is one of this shard's.
        self._bus.subscribe(
            subjects.shard_join_game(self._shard_id), self._on_join_game
        )
        # ...and the answers to the passwords this shard sent away to be checked.
        self._bus.subscribe(subjects.shard_auth(self._shard_id), self._on_auth_result)

    # --- what the gateways report ---------------------------------------------

    def _on_client_event(self, subject: str, payload: str) -> None:
        """One thing that happened on one socket, somewhere out there."""
        event = decode_client_event(payload)
        if event.kind is ClientEventKind.CONNECTED:
            self._client_of[event.conn_id] = self._hub.connect(
                self._sender(event.conn_id), event.conn_id
            )
            _log.info("connection %s registered", event.conn_id)
            # Nothing to say to her yet -- she has not spoken. But her gateway has to be
            # told where to send it when she does, so an empty envelope goes back
            # carrying only the claim.
            self._answer(event.conn_id, "")
        elif event.kind is ClientEventKind.MESSAGE:
            client_id = self._client_of.get(event.conn_id)
            if client_id is not None:  # it closed before this arrived
                self._hub.receive(client_id, event.text)
        elif event.kind is ClientEventKind.RELEASED:
            self._on_released(event.conn_id)
        else:
            self._on_gone(event.conn_id)

    def _on_start_game(self, subject: str, payload: str) -> None:
        """Another shard matched two players and chose this one to run their game.

        Either of them may be a complete stranger here — on a gateway this shard has
        never answered, claimed a moment ago by a shard that is now letting go. So each
        one is registered as a client if she is not already, and the seat that follows is
        what tells her gateway to send her moves here from now on.
        """
        request = decode_start_game(payload)
        _log.info(
            "running a game for %s and %s", request.white.username, request.black.username
        )
        self._hub.start_game(
            self._client_for(request.white), self._client_for(request.black)
        )

    def _on_auth_result(self, subject: str, payload: str) -> None:
        """Somebody's password has been checked, elsewhere, and this is the verdict.

        The connection may have closed in the meantime — a password check is 36 ms, which
        is ample — so an answer for a connection this shard no longer holds is dropped
        here rather than in the lobby, which has already forgotten her.
        """
        result = decode_auth_result(payload)
        client_id = self._client_of.get(result.conn_id)
        if client_id is None:
            _log.info("auth answer for a connection that has gone",
                      extra={"conn": result.conn_id})
            return
        self._hub.authenticated(client_id, result.username, result.rating)

    def _on_join_game(self, subject: str, payload: str) -> None:
        """Somebody typed a room id at another shard, and the room is one of ours."""
        request = decode_join_game(payload)
        client_id, username, rating = self._client_for(request.joiner)
        _log.info("%s sent here for room %s", username, request.room_id)
        self._hub.join_game(client_id, username, rating, request.room_id)

    def _client_for(self, seatee: Seatee) -> Tuple[int, str, int]:
        """This shard's client number, name and rating for one handed-over player."""
        client_id = self._client_of.get(seatee.conn_id)
        if client_id is None:
            client_id = self._hub.connect(self._sender(seatee.conn_id), seatee.conn_id)
            self._client_of[seatee.conn_id] = client_id
        return client_id, seatee.username, seatee.rating

    def _on_released(self, conn_id: str) -> None:
        """This connection has been seated by another shard; it is no longer ours."""
        self._following.pop(conn_id, None)
        self._claimed.discard(conn_id)
        client_id = self._client_of.pop(conn_id, None)
        if client_id is not None:
            self._hub.release(client_id)

    def _on_gone(self, conn_id: str) -> None:
        """A socket closed. Whether that matters is the lobby's to decide: a player
        dropping starts a resign countdown, a spectator leaving is nothing at all."""
        self._following.pop(conn_id, None)
        self._claimed.discard(conn_id)
        client_id = self._client_of.pop(conn_id, None)
        if client_id is not None:
            self._hub.disconnect(client_id)
            _log.info("connection %s gone", conn_id)
        else:
            # TEMPORARY DIAGNOSTIC: a departure for somebody this shard never held.
            _log.warning("departure for a stranger", extra={"conn": conn_id})

    # --- what the shard answers -----------------------------------------------

    def _sender(self, conn_id: str):
        """The lobby's ``send`` for one connection: publish to that connection's mailbox."""

        def send(text: str) -> None:
            self._answer(conn_id, text)

        return send

    def _answer(self, conn_id: str, text: str) -> None:
        """Say something to one connection, and say what changed about it while we are here.

        The three parts of the envelope answer three different questions and are computed
        the same way: each is filled in only the once, on the first message where it has
        become true, so a game in progress costs one field and two ``None``s per delta.
        """
        self._bus.publish(
            subjects.connection(conn_id),
            encode(
                ToClient(
                    text,
                    self._room_to_follow(conn_id),
                    self._claim_for(conn_id),
                )
            ),
        )

    def _claim_for(self, conn_id: str) -> Optional[str]:
        """This shard's name, the first time it answers a connection; then ``None``.

        Answering a connection at all means owning it: either it has just arrived out of
        the queue group, or this shard has just seated the player into a game it runs and
        is taking her over from whoever was holding her. Both are the same sentence to a
        gateway, and neither needs the other shard to be consulted or even to exist.
        """
        if conn_id in self._claimed:
            return None
        self._claimed.add(conn_id)
        return self._shard_id

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
        return self._hub.room_key(game_id)

    def _publish(self, subject: str, text: str) -> None:
        """The lobby's room sink: one publish for a whole room, whoever is in it."""
        self._bus.publish(subject, text)

    # --- time ------------------------------------------------------------------

    def tick(self, dt_ms: int) -> None:
        """Advance every game this shard is running, and say that it is still running."""
        self._hub.tick(dt_ms)
        ACTIVE_GAMES.set(self._hub.game_count)
        # Published so that "every socket is held by exactly one shard" stops being an
        # assumption and becomes a query: summed across the shards this equals the
        # gateways' connection count, and when it does not, a disconnect went astray.
        CLIENTS.set(len(self._client_of))
        self._heartbeat(dt_ms)

    def _heartbeat(self, dt_ms: int) -> None:
        """Every ``SHARD_HEARTBEAT_MS``, tell the pool this shard is alive and how busy.

        On the tick, rather than when a game starts or ends, because the message is
        "still here" and not "something changed" — a shard whose game count is steady is
        exactly the one whose silence would be mistaken for death.
        """
        self._since_heartbeat_ms += dt_ms
        if self._since_heartbeat_ms >= SHARD_HEARTBEAT_MS:
            self._since_heartbeat_ms = 0
            self._allocator.announce(self._shard_id, self._hub.game_count)

    def next_event_delay_ms(self) -> Optional[int]:
        """When this shard next has something to do — see :func:`next_sleep_s`."""
        return self._hub.next_event_delay_ms()

    @property
    def clients(self) -> int:
        """How many connections this shard is holding — for logs, health, and tests.

        The mirror of :attr:`kfchess.gateway.app.Gateway.connections`, and the number
        that would quietly climb for ever if a shard were not told when a connection it
        was holding has been seated somewhere else.
        """
        return len(self._client_of)


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
    from kfchess.config import NATS_URL, OBS_PORT, REDIS_URL, SHARD_ID
    from kfchess.obs.endpoint import serve_observability
    from kfchess.services.shared import SharedState
    from kfchess.services.store import connect as connect_store

    serve_observability(OBS_PORT)
    bus = await connect(nats_url or NATS_URL)
    shared = SharedState.on(connect_store(REDIS_URL), SHARD_ID)
    shard = Shard(bus, new_board, UserStore(), shared)

    await asyncio.gather(bus.run(), run_games(shard, tick_ms))
