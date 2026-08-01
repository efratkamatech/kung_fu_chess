"""ConnectionRouter: which sockets this gateway holds, and which rooms it follows.

Pure bookkeeping — two dictionaries and the arithmetic that keeps them honest. It touches
no bus and no socket, so every rule in it is a plain function call in a test.

The rule that matters is the one about rooms. A gateway follows a room's subject **once**,
no matter how many of its connections are in that room, and fans each message out locally.
Subscribing per connection would mean a room with a dozen people on one gateway pulling a
dozen copies of every delta across the network — the exact cost the room subjects exist to
avoid, reintroduced at the last hop. So :meth:`follow` reports whether this is the *first*
connection here to want that room, and :meth:`close` reports which rooms nobody here wants
any more; the caller subscribes and unsubscribes on those answers alone.

Spectators are why that is not a theoretical concern. Players come in twos, but a popular
room's watchers all land on the same handful of gateways, and each of them is another
connection wanting the same subject.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Set

# How a gateway pushes one wire string to one socket. The router never calls it for a
# connection it has closed, which is the whole reason it holds them rather than the caller.
Send = Callable[[str], None]


class ConnectionRouter:
    """The connections one gateway holds, indexed by id and by room."""

    def __init__(self, gateway_id: str) -> None:
        self._gateway_id = gateway_id
        self._next_number = 0
        self._sends: Dict[str, Send] = {}
        # room key -> the connections here following it. A room with an entry has a live
        # subscription; a room with no entry has none, and the two never disagree because
        # only follow() and close() touch this.
        self._rooms: Dict[str, Set[str]] = {}
        self._room_of: Dict[str, str] = {}
        # Which shard each connection belongs to, once one has claimed it, and what the
        # client said before that answer arrived. The gap is real: a socket opens and the
        # player's login is on its way before any shard has replied, and the whole point
        # of the claim is that those two messages must not be answered by different
        # shards. So the gateway holds them for the moment it takes, in order.
        self._owner: Dict[str, str] = {}
        self._held: Dict[str, List[str]] = {}

    def open(self, send: Send) -> str:
        """Register a new socket and return the id the shard will address it by.

        The id begins with this gateway's own, so the reply subject
        (``conn.{conn_id}``) is matched by this gateway's subscription and by no other
        gateway's — see :func:`kfchess.bus.subjects.gateway_inbox`.
        """
        conn_id = f"{self._gateway_id}.{self._next_number}"
        self._next_number += 1
        self._sends[conn_id] = send
        return conn_id

    def owner(self, conn_id: str) -> Optional[str]:
        """Which shard this connection belongs to, or ``None`` if none has claimed it."""
        return self._owner.get(conn_id)

    def hold(self, conn_id: str, text: str) -> None:
        """Keep what a client said until a shard claims her — see :meth:`claim`."""
        self._held.setdefault(conn_id, []).append(text)

    def claim(self, conn_id: str, shard_id: str) -> List[str]:
        """Record this connection's owner, and hand back anything held for it.

        Called on a *first* claim and on a handover alike: a shard that seats a player
        into a game it runs takes her connection from whichever shard was holding it, and
        this is the whole of what changes. The held messages come back in the order they
        were said, which is the order they must be sent in.
        """
        self._owner[conn_id] = shard_id
        return self._held.pop(conn_id, [])

    def close(self, conn_id: str) -> List[str]:
        """Forget a socket, and report the rooms this gateway no longer needs.

        The returned rooms are the ones whose last local follower has just left; the
        caller unsubscribes from exactly those. An unknown id answers with nothing, so a
        socket that closes twice is harmless.
        """
        self._sends.pop(conn_id, None)
        self._owner.pop(conn_id, None)
        self._held.pop(conn_id, None)
        room = self._room_of.pop(conn_id, None)
        if room is None:
            return []
        followers = self._rooms[room]
        followers.discard(conn_id)
        if followers:
            return []  # others here are still watching this room
        del self._rooms[room]
        return [room]

    def follow(self, conn_id: str, room: str) -> bool:
        """Note that ``conn_id`` is now in ``room``; answer whether to subscribe.

        ``True`` only for the first connection here to enter that room. Everyone after
        rides the subscription it opened — the second player, and every spectator.
        """
        if conn_id not in self._sends:
            return False  # it closed between the shard's answer and this arriving
        self._room_of[conn_id] = room
        followers = self._rooms.setdefault(room, set())
        first = not followers
        followers.add(conn_id)
        return first

    def to_connection(self, conn_id: str) -> Optional[Send]:
        """How to reach one connection, or ``None`` if it is no longer here."""
        return self._sends.get(conn_id)

    def in_room(self, room: str) -> List[Send]:
        """How to reach everyone here who is in ``room`` — players and watchers alike."""
        return [
            self._sends[conn_id]
            for conn_id in self._rooms.get(room, ())
            if conn_id in self._sends
        ]

    def __len__(self) -> int:
        """How many sockets this gateway is holding (for logs and health)."""
        return len(self._sends)
