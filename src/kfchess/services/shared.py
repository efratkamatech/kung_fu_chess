"""Everything the shards share, built in one place and handed to the lobby.

Three services, one store between them, and one decision: which store. That decision is
the whole difference between the two ways this game runs, and it is made **here and
nowhere else** — the lobby is handed the result and cannot tell which it got, the shard
passes it through, and the rules never see it at all.

    SharedState.on()             # one process: a dictionary. No Redis, no Docker.
    SharedState.on(redis_store)  # many processes: the same code, one authority.

Keeping the choice to a single line is the point. A server that "supports running
locally" by growing an ``if`` in every method supports it for about a month; this way the
local mode is not a mode, it is the same object graph with a smaller store underneath,
and there is no second code path to keep honest.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from kfchess.config import SHARD_ID
from kfchess.services.allocator import Allocator
from kfchess.services.directory import PlayerDirectory
from kfchess.services.matchmaker import Matchmaker, wall_clock_ms
from kfchess.services.rooms import Rooms, random_id
from kfchess.services.store import InMemoryKeyValueStore, KeyValueStore


@dataclass(frozen=True)
class SharedState:
    """The room ids, the queue, the directory and the shard pool, over one store."""

    rooms: Rooms
    matchmaker: Matchmaker
    directory: PlayerDirectory
    allocator: Allocator
    # Who *this* process is, in the directory's answers. A seat records the shard running
    # it, and a shard reading one back has to recognise its own name to know whether the
    # game is here or somewhere it will have to send the player instead.
    shard_id: str = SHARD_ID

    @classmethod
    def on(
        cls,
        store: Optional[KeyValueStore] = None,
        shard_id: str = SHARD_ID,
        generate_id: Callable[[], str] = random_id,
        now_ms: Callable[[], int] = wall_clock_ms,
    ) -> "SharedState":
        """Build the three services over ``store``, or over this process if none is given.

        ``generate_id`` and ``now_ms`` are here because they are what a test has to pin
        down — a known sequence of room ids, a clock that does not tick unless asked —
        and reaching past this constructor to inject them would mean building all three
        services by hand at every call site.
        """
        store = store if store is not None else InMemoryKeyValueStore()
        return cls(
            rooms=Rooms(store, shard_id, generate_id=generate_id),
            matchmaker=Matchmaker(store, now_ms=now_ms),
            directory=PlayerDirectory(store),
            allocator=Allocator(store),
            shard_id=shard_id,
        )
