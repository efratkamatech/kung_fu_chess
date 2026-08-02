"""Which shard should run the next game — and which shards are still alive to run one.

Two questions, and the second is the one that makes the first hard. Picking the least
loaded shard is a sorted set. Knowing that a shard *is* a shard, rather than a name left
behind by a process that died an hour ago, is not: nothing tells anybody when a machine
stops, and a pool that trusts its own membership list will keep sending games to a
corpse.

So a shard says "still here" on a short-lived key, and that key is the only evidence of
life. Nothing sweeps the pool, exactly as nothing sweeps the matchmaking queue and for
the same reason: a dead shard is discovered by whoever next tries to use it, at the cost
of the lookup they were making anyway. The alternative — a reaper walking every shard on
a timer — is work proportional to the size of the cluster, performed constantly, to learn
something that is only ever needed at the moment of allocation.

The allocation itself is **deliberately simple**: least loaded wins, and that is all.
No consistent hashing, no rebalancing, no draining. Games here last thirty to ninety
seconds, so any imbalance a naive choice creates has undone itself within a minute and a
half. A rebalancer would spend more of the design's complexity budget than the imbalance
costs.
"""

from __future__ import annotations

from typing import Optional

from kfchess.config import SHARD_TTL_S
from kfchess.services.store import KeyValueStore

# The pool, scored by how many games each shard is running. One ranking, so "who is least
# busy" is a range query rather than a walk over every shard's key.
POOL = "shard:load"


class Allocator:
    """Keeps the pool of live shards, and picks one to run a new game."""

    def __init__(self, store: KeyValueStore, ttl_s: int = SHARD_TTL_S) -> None:
        self._store = store
        self._ttl_s = ttl_s

    def announce(self, shard_id: str, games: int) -> None:
        """Say that ``shard_id`` is alive and running ``games`` of them.

        Called on a heartbeat rather than when the count changes: the point is the
        *liveness*, and a shard whose game count happens to be stable is exactly the one
        whose silence would otherwise be indistinguishable from death.
        """
        self._store.set(_alive_key(shard_id), str(games), ttl_s=self._ttl_s)
        self._store.add_to_ranking(POOL, shard_id, games)

    def allocate(self) -> Optional[str]:
        """The least loaded shard that is still alive, or ``None`` if there are none.

        Anything found dead on the way is taken out of the pool for good, so this cannot
        spin: each turn of the loop either answers or removes a member.

        ``None`` means every shard is gone — there is nowhere to put a game. The caller
        has to say so rather than pretend, which is why this is not "raise" either: a
        cluster with nothing left in it is a state the lobby can report to a player.
        """
        while True:
            found = self._store.first_in_range(POOL, 0, float("inf"))
            if found is None:
                return None
            shard_id, _ = found
            if self._store.get(_alive_key(shard_id)) is not None:
                return shard_id
            self._store.remove_from_ranking(POOL, shard_id)

    def retire(self, shard_id: str) -> None:
        """Take a shard out of the pool on purpose — it is shutting down, not dying.

        Not required for correctness: the key would expire on its own, which is what
        covers the shard that does *not* get to say goodbye. This only shortens the
        window in which new games are sent somewhere that has stopped accepting them.
        """
        self._store.delete(_alive_key(shard_id))
        self._store.remove_from_ranking(POOL, shard_id)


def _alive_key(shard_id: str) -> str:
    """Where one shard's proof of life lives. One place, so nothing spells it differently."""
    return f"shard:{shard_id}:alive"
