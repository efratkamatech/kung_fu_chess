"""The rooms service: room ids that are unique across every shard, not just one.

:class:`~kfchess.server.room_manager.RoomManager` kept its ids in a dictionary, which
made them unique on *one* machine. That is not the same property, and the difference is
not theoretical: two shards drawing ``7C2FQK`` in the same second would each look in
their own dictionary, each see it free, and each hand it to a player. Two rooms, one id,
and whichever joiner typed it would land in a coin toss.

The check has to happen somewhere both of them agree is the authority, and it has to be
one operation rather than a look followed by a write — between the two, the other shard
writes. ``SET key value NX`` is that operation: it claims the name and tells you whether
the name was yours to claim.

Two smaller things come free with it. A room key carries **which shard is running that
room**, which is what a second shard needs in order to route a joiner it cannot see. And
it carries a **time to live**, so an id held by a shard that crashed is not held for ever
— nothing has to notice the crash or tidy up after it.
"""

from __future__ import annotations

from typing import Callable, Optional

from kfchess.config import ROOM_ID_MAX_ATTEMPTS, ROOM_TTL_S
from kfchess.server.room_manager import RoomIdUnavailable, random_id


class Rooms:
    """Hands out room ids that no other shard can be holding, and says who holds one."""

    def __init__(
        self,
        store,
        shard_id: str,
        ttl_s: int = ROOM_TTL_S,
        generate_id: Callable[[], str] = random_id,
    ) -> None:
        self._store = store
        self._shard_id = shard_id
        self._ttl_s = ttl_s
        self._generate_id = generate_id

    def create(self) -> str:
        """Claim a fresh room id for this shard, and return it.

        Raises :class:`~kfchess.server.room_manager.RoomIdUnavailable` after
        :data:`~kfchess.config.ROOM_ID_MAX_ATTEMPTS` tries, for the same reason the
        single-process version does: a bounded failure a player can be told about beats
        an unbounded loop on the thread that runs every game here.
        """
        for _ in range(ROOM_ID_MAX_ATTEMPTS):
            room_id = self._generate_id()
            if self._store.set(
                _key(room_id), self._shard_id, ttl_s=self._ttl_s, unless_exists=True
            ):
                return room_id
        raise RoomIdUnavailable(f"no free room id in {ROOM_ID_MAX_ATTEMPTS} attempts")

    def shard_of(self, room_id: str) -> Optional[str]:
        """Which shard is running ``room_id``, or ``None`` if no such room is open.

        The answer a joiner needs and a single shard could not give: the room may well be
        somewhere else entirely.
        """
        return self._store.get(_key(room_id))

    def close(self, room_id: str) -> None:
        """Give up an id when its game is over, rather than waiting out its life."""
        self._store.delete(_key(room_id))


def _key(room_id: str) -> str:
    """The store key for one room. One place, so nothing can spell it differently."""
    return f"room:{room_id}"
