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
- ``lobby.cmd`` — a socket has just opened and belongs to nobody yet. **Every shard
  subscribes to this one in the same queue group**, so exactly one of them receives each
  new connection and claims it; the rest never hear of it. This is the only subject in
  the system that is answered by "whoever is free" rather than by name.
- ``shard.{shard_id}.cmd`` — everything that connection says afterwards. The shard that
  claimed it told the gateway so, and the gateway has published there ever since.

The pairing of those last two is what makes a second shard possible. It used to be one
subject for both jobs, which worked exactly as long as there was one shard: with two,
each would have received every login and run its own copy of every game that followed.

A connection's owner can **change hands**, and exactly one thing changes it: being seated
in a game that another shard is running. The shard that seats her claims her in the same
breath, and from then on her moves arrive where her game is. Nothing else moves a
connection, and no shard ever asks another for one.
"""

from __future__ import annotations

# Where a connection nobody owns yet is announced. See the note above.
LOBBY_CMD = "lobby.cmd"

# The queue group every shard subscribes to LOBBY_CMD under. A group name is part of the
# wire contract exactly as a subject is -- two shards that spelled it differently would
# each get their own copy, which is the bug this exists to prevent -- so it lives here
# with the subjects rather than in whichever file happens to subscribe.
SHARD_GROUP = "shards"

# NATS wildcards: ``*`` matches one token, ``>`` matches the rest of the subject.
_MATCH_REST = ">"


def connection(conn_id: str) -> str:
    """One connection's mailbox, for a message meant only for that client.

    ``conn_id`` is opaque to the shard — it was minted by a gateway and already carries
    which one, so addressing a reply is a prefix and never a lookup.
    """
    return f"conn.{conn_id}"


def shard_cmd(shard_id: str) -> str:
    """Everything from the connections one shard has claimed.

    Addressed by name, not by availability: the whole point is that the same shard keeps
    receiving the same connection, because it is the one holding what it knows about her.
    """
    return f"shard.{shard_id}.cmd"


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
