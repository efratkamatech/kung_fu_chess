"""Subject names for the message bus — the addresses the services publish to.

Where :mod:`kfchess.bus.topics` names the channels of the *in-process* event bus, this
names the channels *between processes*: the gateway holding the sockets and the shard
running the games. Same rule as topics, for the same reason — a publisher and its
subscribers have to agree on the exact string, so the string exists once.

A subject here is built from parts, not written out, because every one of them carries
an id. The layout is three groups:

- ``conn.{conn_id}`` — one connection's own mailbox, where the shard answers a single
  client (a Welcome, a refusal, a seat). A connection id begins with the id of the
  gateway that minted it, so a gateway can follow ``conn.{its own id}.>`` and be handed
  exactly the traffic for the sockets it holds and nothing else. The shard never takes
  that id apart: it prefixes ``conn.`` and publishes. This is what lets a second gateway
  exist without either of them knowing about the other.
- ``room.{room_id}.delta`` / ``.state`` — one game's broadcast, and the reason the design
  scales. The shard publishes a delta **once**, however many people are in that room, and
  every gateway with a member there gets one copy to fan out locally. Publishing per
  client instead would put the whole fan-out on the shard.

  This is also what makes a spectator nearly free. Watching a game is *subscribing to a
  subject* — the shard does not address spectators, count them, or know which gateway
  holds them, and a room with two players and fifty watchers costs it exactly what a room
  with two players costs. Nothing here distinguishes a player from a watcher, because at
  this layer there is no difference: the difference is that one of them may also publish
  to ``lobby.cmd``, and the shard is what refuses the other.
- ``lobby.cmd`` — everything a client says before it belongs to a room: log in, look for
  a game, open or join a private room, and the bare fact that a socket opened or closed.

That last one is **temporary and deliberately so.** It works because S2 has exactly one
shard; with several, every shard would receive every login. S3 dissolves it — login goes
to Auth, seeking goes to the Matchmaker, room ids come from the Rooms service — and this
constant disappears with the ``Lobby`` that answers it today.
"""

from __future__ import annotations

# The pre-room channel: client -> the one shard. See the note above; S3 removes it.
LOBBY_CMD = "lobby.cmd"

# NATS wildcards: ``*`` matches one token, ``>`` matches the rest of the subject.
_MATCH_REST = ">"


def connection(conn_id: str) -> str:
    """One connection's mailbox, for a message meant only for that client.

    ``conn_id`` is opaque to the shard — it was minted by a gateway and already carries
    which one, so addressing a reply is a prefix and never a lookup.
    """
    return f"conn.{conn_id}"


def gateway_inbox(gateway_id: str) -> str:
    """Everything addressed to any connection this gateway holds."""
    return f"conn.{gateway_id}.{_MATCH_REST}"


def room_delta(room_id: str) -> str:
    """One game's stream of what happened — the ordinary traffic of a game in play."""
    return f"room.{room_id}.delta"


def room_state(room_id: str) -> str:
    """One game's full snapshots: a seat, a reconnect, and the periodic resync."""
    return f"room.{room_id}.state"


def room_inbox(room_id: str) -> str:
    """Everything a gateway wants from one room, deltas and snapshots alike."""
    return f"room.{room_id}.{_MATCH_REST}"


def room_of(subject: str) -> str:
    """Which room a ``room.*`` subject belongs to — the inverse of the three above."""
    return subject.split(".")[1]


def connection_of(subject: str) -> str:
    """Which connection a ``conn.*`` subject is addressed to."""
    return subject.split(".", 1)[1]
