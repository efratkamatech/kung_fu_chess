"""The solo server: the whole thing, in one process, with nothing installed.

Two players on a laptop, or one person testing a change, should not have to bring up a
message broker, a cache and a database to move a rook. Before the gateway and the shard
were split apart this was simply how the server ran; keeping it is a deliberate decision,
not nostalgia.

**It is not a second implementation, and that is the entire point.** The same
:class:`~kfchess.gateway.app.Gateway` holds the sockets, the same
:class:`~kfchess.server.shard.Shard` runs the games, and the same
:class:`~kfchess.server.lobby.Lobby` decides everything either of them is asked. What
changes is two objects underneath them:

- the message bus between gateway and shard is
  :class:`~kfchess.bus.message_bus.InProcessMessageBus` rather than NATS — a publish is a
  function call, because both ends are in this interpreter;
- the shared state is an :class:`~kfchess.services.store.InMemoryKeyValueStore` rather
  than Redis — a single process agreeing with itself needs no third party to agree
  through.

So there is no "local mode" branch anywhere in the game, the lobby, the rooms or the
matchmaking. There is this file, which picks the two, and everything above it is unable
to tell. A bug found here is a bug there.

The client cannot tell either: it opens one WebSocket to ``ws://localhost:8765`` and
speaks the same protocol, exactly as it does to a gateway with four containers behind it.
"""

from __future__ import annotations

import logging

from kfchess.bus.message_bus import InProcessMessageBus
from kfchess.config import GATEWAY_ID
from kfchess.gateway.app import Gateway
from kfchess.server.lobby import NewBoard
from kfchess.server.shard import Shard
from kfchess.server.user_store import UserStore
from kfchess.services.shared import SharedState

_log = logging.getLogger(__name__)  # silent until configure_logging runs


def build(new_board: NewBoard, users: UserStore = None):
    """Wire a gateway and a shard to each other in this process; return both.

    Separate from :func:`serve` because everything here is synchronous and decided, and
    everything there is a socket. A test can hold both ends of this and play a whole
    game without an event loop — which is what ``test_gateway_shard_e2e`` already does,
    with the same two objects.
    """
    bus = InProcessMessageBus()
    shard = Shard(bus, new_board, users if users is not None else UserStore(), SharedState.on())
    return Gateway(bus, GATEWAY_ID), shard


async def serve(  # pragma: no cover  (irreducible async socket + timer I/O)
    new_board: NewBoard,
    host: str = None,
    port: int = None,
    tick_ms: int = None,
) -> None:
    """Run the game on one machine until cancelled: sockets, games, and nothing else.

    No NATS, no Redis, no database server, no Docker. The listener and the clock are the
    same two coroutines the split deployment runs; they are simply in the same process
    here, and the bus between them is a function call.
    """
    from kfchess.gateway.app import listen
    from kfchess.server.shard import run_games

    gateway, shard = build(new_board)
    _log.info("solo server starting on %s:%s", host, port)
    async with await listen(gateway, host, port):
        await run_games(shard, tick_ms)
