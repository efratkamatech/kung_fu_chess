"""The rooms service: room ids that are unique across every shard, not just one.

A room is a game you reach by a short shareable id (``"7C2FQK"``) instead of by
matchmaking. This owns the id bookkeeping and nothing else — it knows no players, no
colours and no sockets; the :class:`~kfchess.server.lobby.Lobby` seats joiners itself.

It used to keep the ids in a dictionary, which made them unique on *one* machine. That is
not the same property, and the difference is not theoretical: two shards drawing
``7C2FQK`` in the same second would each look in their own dictionary, each see it free,
and each hand it to a player. Two rooms, one id, and whichever joiner typed it would land
in a coin toss.

The check has to happen somewhere both of them agree is the authority, and it has to be
one operation rather than a look followed by a write — between the two, the other shard
writes. ``SET key value NX`` is that operation: it claims the name and tells you whether
the name was yours to claim. When there is only one shard, the store it claims against is
a dictionary in the same process and the answer is the same answer.

So there are two maps here, and they are two different questions:

- **which shard runs this room** lives in the store, because a joiner may be talking to a
  shard that has never heard of the room. This is what makes the id global.
- **which of *my* games this room is** stays local, because a game object exists in
  exactly one process and no other process could use the answer anyway.

The stored one carries a **time to live**, so an id held by a shard that crashed is not
held for ever — nothing has to notice the crash or tidy up after it.
"""

from __future__ import annotations

import secrets
from typing import Callable, Dict, Optional

from kfchess.config import (
    ROOM_ID_ALPHABET,
    ROOM_ID_LENGTH,
    ROOM_ID_MAX_ATTEMPTS,
    ROOM_TTL_S,
    SHARD_ID,
)
from kfchess.services.store import InMemoryKeyValueStore, KeyValueStore


class RoomIdUnavailable(RuntimeError):
    """No free room id turned up within :data:`~kfchess.config.ROOM_ID_MAX_ATTEMPTS`."""


def random_id() -> str:
    """A short, shareable room id from the unambiguous alphabet, e.g. ``"7C2FQK"``.

    ``secrets`` rather than ``random``, because a guessable id is an open door into
    somebody else's game.
    """
    return "".join(secrets.choice(ROOM_ID_ALPHABET) for _ in range(ROOM_ID_LENGTH))


class Rooms:
    """Claims room ids no other shard can be holding, and maps them to local games."""

    def __init__(
        self,
        store: Optional[KeyValueStore] = None,
        shard_id: str = SHARD_ID,
        ttl_s: int = ROOM_TTL_S,
        generate_id: Callable[[], str] = random_id,
    ) -> None:
        """Take a store to claim ids in; default to one in this process.

        The default is what makes a solo server work with no Redis: a single process
        agreeing with itself needs no third party to agree through. Pass a Redis-backed
        store and the identical code claims ids against every other shard as well.

        The id generator is injected too, so a test can feed a known sequence — including
        a forced collision — with no randomness in it.
        """
        self._store = store if store is not None else InMemoryKeyValueStore()
        self._shard_id = shard_id
        self._ttl_s = ttl_s
        self._generate_id = generate_id
        self._game_by_room: Dict[str, int] = {}
        self._room_by_game: Dict[int, str] = {}

    def create(self, game_id: int) -> str:
        """Claim a fresh room id for ``game_id`` on this shard, and return it.

        Raises :class:`RoomIdUnavailable` after
        :data:`~kfchess.config.ROOM_ID_MAX_ATTEMPTS` tries. The bound is the whole point:
        this used to redraw until it found a free id, and the thread it would have spun
        on for ever is the one thread that runs every game on this shard.
        """
        for _ in range(ROOM_ID_MAX_ATTEMPTS):
            room_id = self._generate_id()
            if self._store.set(
                _key(room_id), self._shard_id, ttl_s=self._ttl_s, unless_exists=True
            ):
                self._game_by_room[room_id] = game_id
                self._room_by_game[game_id] = room_id
                return room_id
        raise RoomIdUnavailable(f"no free room id in {ROOM_ID_MAX_ATTEMPTS} attempts")

    def game_for(self, room_id: str) -> Optional[int]:
        """The local game behind ``room_id``, or ``None`` if this shard does not run it.

        ``None`` covers two different situations, which is why :meth:`shard_of` exists
        alongside it: there is no such room anywhere, or there is one and it is somewhere
        else. Today those get the same answer — a player is told the room is unknown —
        because there is one shard and the two cases coincide.
        """
        return self._game_by_room.get(room_id)

    def shard_of(self, room_id: str) -> Optional[str]:
        """Which shard is running ``room_id``, or ``None`` if no such room is open.

        The answer no single shard could give from its own memory. It is what a joiner
        needs once there is more than one shard to be joined to, and it is already true
        now — every id claimed above is claimed *with its shard's name on it*.
        """
        return self._store.get(_key(room_id))

    def remove_game(self, game_id: int) -> None:
        """Give up a finished game's room id, rather than waiting out its life.

        A no-op for a matchmade game, which was never registered under a room id. All
        three records go together, so none can outlive the others.
        """
        room_id = self._room_by_game.pop(game_id, None)
        if room_id is not None:
            del self._game_by_room[room_id]
            self._store.delete(_key(room_id))


def _key(room_id: str) -> str:
    """The store key for one room. One place, so nothing can spell it differently."""
    return f"room:{room_id}"
