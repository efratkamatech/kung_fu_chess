"""The shared key-value store: Redis, and an in-memory one that behaves like it.

The services above this file need three things of it, and the third is the interesting
one:

- read a key, and delete a key;
- write a key that **expires by itself**, so state stranded by a crashed process is not
  stranded for ever;
- write a key **only if nobody else already has**, and be told which of those happened.

That last one is why this is Redis and not a dictionary. Two shards inventing a room id
at the same instant is not a race a shard can win by checking first and writing second —
between the check and the write, the other one writes. ``SET key value NX`` decides it in
one operation, at one place that both of them agree is the authority, and the answer to
"was it me?" comes back with it.

:class:`InMemoryKeyValueStore` implements the same three inside one process, against an
injected clock — so a test can watch a key expire without waiting for it, and so the solo
server runs a whole game with no Redis anywhere. Which of the two is in play is a
deployment decision: one process sharing state with itself needs no server to share it
through, and only stops being enough at the point a second process exists.

It is not a Redis emulator and does not try to be: it implements exactly the operations
this project uses, which is what keeps "it works against the in-memory one" an honest
claim about the other.
"""

from __future__ import annotations

import time
from typing import Callable, Dict, Optional, Protocol, Tuple


class KeyValueStore(Protocol):
    """What a service needs of a store, written down rather than described.

    Both implementations below satisfy it and neither inherits from it: it exists so that
    every ``store`` parameter in this package says what it will be used for. It was prose
    in four docstrings before, which is the same information in the place where nothing
    can check it.
    """

    def get(self, key: str) -> Optional[str]:
        """The value at ``key``, or ``None`` if it is absent or has expired."""

    def set(
        self,
        key: str,
        value: str,
        ttl_s: Optional[int] = None,
        unless_exists: bool = False,
    ) -> bool:
        """Write ``value`` at ``key``; answer whether it was written."""

    def delete(self, key: str) -> None:
        """Forget ``key``. Deleting one that is not there is not an error."""

    def add_to_ranking(self, key: str, member: str, score: float) -> None:
        """Put ``member`` in the ranking at ``key`` with ``score``."""

    def remove_from_ranking(self, key: str, member: str) -> None:
        """Take ``member`` out of a ranking; one that is not there is not an error."""

    def first_in_range(
        self, key: str, low: float, high: float, reverse: bool = False
    ) -> Optional[Tuple[str, float]]:
        """The lowest-scoring member within ``[low, high]``, or the highest if reversed."""


def monotonic_s() -> float:
    """The local clock in seconds — a duration source, not a wall-clock time."""
    return time.monotonic()


class InMemoryKeyValueStore:
    """The shared state of a single process: the same operations, no server.

    Expiry is evaluated when a key is read rather than swept in the background, which is
    indistinguishable from the outside and means a test never has to wait for anything.
    """

    def __init__(self, now_s: Callable[[], float] = monotonic_s) -> None:
        self._now_s = now_s
        # key -> (value, expires_at or None for "keep it until something deletes it")
        self._values: Dict[str, Tuple[str, Optional[float]]] = {}
        # key -> {member: score}. Kept apart from the values above exactly as Redis keeps
        # them apart: a ranking is read by score range, never by name.
        self._rankings: Dict[str, Dict[str, float]] = {}

    def get(self, key: str) -> Optional[str]:
        """The value at ``key``, or ``None`` if it is absent or has expired."""
        entry = self._values.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if expires_at is not None and expires_at <= self._now_s():
            del self._values[key]
            return None
        return value

    def set(
        self,
        key: str,
        value: str,
        ttl_s: Optional[int] = None,
        unless_exists: bool = False,
    ) -> bool:
        """Write ``value`` at ``key``; answer whether it was written.

        ``ttl_s`` makes the key expire on its own. ``unless_exists`` (Redis's ``NX``)
        writes only if the key is free, and is what makes claiming a name safe between
        processes: the answer is ``False`` when somebody else got there first.
        """
        if unless_exists and self.get(key) is not None:
            return False
        expires_at = None if ttl_s is None else self._now_s() + ttl_s
        self._values[key] = (value, expires_at)
        return True

    def delete(self, key: str) -> None:
        """Forget ``key``. Deleting one that is not there is not an error."""
        self._values.pop(key, None)

    # --- rankings: a set of members kept sorted by a number ---------------------

    def add_to_ranking(self, key: str, member: str, score: float) -> None:
        """Put ``member`` in the ranking at ``key`` with ``score`` (Redis ``ZADD``)."""
        self._rankings.setdefault(key, {})[member] = score

    def remove_from_ranking(self, key: str, member: str) -> None:
        """Take ``member`` out of a ranking; one that is not there is not an error."""
        self._rankings.get(key, {}).pop(member, None)

    def first_in_range(
        self, key: str, low: float, high: float, reverse: bool = False
    ) -> Optional[Tuple[str, float]]:
        """The lowest-scoring member within ``[low, high]``, or the highest if reversed.

        Redis ``ZRANGEBYSCORE key low high LIMIT 0 1``, and ``ZREVRANGEBYSCORE`` for the
        other direction. **One** member, not the range: asking for everything in a window
        and picking from it is O(how many are in the window), which at the sizes this
        design is for is the same linear scan it was meant to replace. Asking for the
        nearest one in each direction is two queries and O(log n).
        """
        matching = sorted(
            (score, member)
            for member, score in self._rankings.get(key, {}).items()
            if low <= score <= high
        )
        if not matching:
            return None
        score, member = matching[-1] if reverse else matching[0]
        return member, score


class RedisKeyValueStore:  # pragma: no cover  (a live Redis; the in-memory one stands in)
    """The store for many processes: the same operations, straight onto ``redis-py``.

    Deliberately the thinnest possible skin, for the same reason as
    :class:`~kfchess.bus.message_bus.NatsMessageBus`: everything that decides *what* to
    store lives in the services, which are driven in one process by the class above, and
    what is left here is argument names and a decode.
    """

    def __init__(self, client) -> None:
        """Wrap a connected ``redis-py`` client (see :func:`connect`).

        ``client`` is left untyped: it is ``redis.Redis``, and naming it here would mean
        importing the library at module scope, which is exactly what this file avoids so
        that a machine without it can still run everything else.
        """
        self._client = client

    def get(self, key: str) -> Optional[str]:
        value = self._client.get(key)
        return None if value is None else value.decode("utf-8")

    def set(
        self,
        key: str,
        value: str,
        ttl_s: Optional[int] = None,
        unless_exists: bool = False,
    ) -> bool:
        # redis-py returns True on a write and None when NX declined it.
        return bool(self._client.set(key, value, ex=ttl_s, nx=unless_exists))

    def delete(self, key: str) -> None:
        self._client.delete(key)

    def add_to_ranking(self, key: str, member: str, score: float) -> None:
        self._client.zadd(key, {member: score})

    def remove_from_ranking(self, key: str, member: str) -> None:
        self._client.zrem(key, member)

    def first_in_range(
        self, key: str, low: float, high: float, reverse: bool = False
    ) -> Optional[Tuple[str, float]]:
        if reverse:
            rows = self._client.zrevrangebyscore(
                key, high, low, start=0, num=1, withscores=True
            )
        else:
            rows = self._client.zrangebyscore(
                key, low, high, start=0, num=1, withscores=True
            )
        if not rows:
            return None
        member, score = rows[0]
        return member.decode("utf-8"), score


def connect(url: str) -> RedisKeyValueStore:  # pragma: no cover  (opens a socket)
    """Connect to the Redis at ``url`` and wrap it.

    ``redis`` is imported here rather than at module scope so that a machine without the
    client library still imports — and tests — everything else.
    """
    import redis

    return RedisKeyValueStore(redis.Redis.from_url(url))
