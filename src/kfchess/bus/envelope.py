"""The envelope: what a gateway and a shard say to each other about a client.

The messages the *player* sends and receives are already defined — that is
:mod:`kfchess.shared.protocol`, and the gateway does not read a word of it. What is
missing is the sentence around it: *which connection* this came from, and *which
connection* this is for. That is all an envelope is.

Keeping it separate is what keeps the gateway dumb, which is the property the whole split
is built on. A gateway that had to look inside a ``Seated`` message to learn that this
player is now in room 7 would be a gateway that knows the rules of the game; one file
later it would be deciding something. So the shard says it in the envelope instead —
:attr:`ToClient.join_room` — and the gateway follows an instruction it cannot
misinterpret, having never parsed the payload it is carrying.

The payload therefore travels as **opaque text**, start to finish. The gateway moves
strings between a socket and a subject and is incapable of doing anything else with them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

from kfchess.shared.codes import WireEnum


class ClientEventKind(WireEnum):
    """What can be said about a connection on a shard's inbox.

    The first three are a gateway reporting on a socket. The fourth is one shard telling
    another that a connection it was holding has been seated elsewhere and is no longer
    its concern — the same subject, because it is the same subject matter: something has
    happened to a connection you know about.
    """

    CONNECTED = "connected"        # a socket opened; nothing has been said on it yet
    MESSAGE = "message"            # the client sent this text
    DISCONNECTED = "disconnected"  # the socket closed, cleanly or otherwise
    RELEASED = "released"          # another shard has taken this connection over


@dataclass(frozen=True)
class ClientEvent:
    """Gateway -> shard: something happened on a connection.

    ``conn_id`` is unique across every gateway (see
    :func:`kfchess.bus.subjects.connection`), so the shard can address a reply to it
    without knowing or caring which gateway is holding the socket. That is exactly the
    property that lets a player reconnect to a different gateway and carry on.
    """

    kind: ClientEventKind
    conn_id: str
    text: str = ""  # the client's wire message, verbatim; empty for connect/disconnect

    def to_dict(self) -> dict:
        return {"kind": self.kind, "conn_id": self.conn_id, "text": self.text}

    @classmethod
    def from_dict(cls, data: dict) -> "ClientEvent":
        return cls(
            ClientEventKind(data["kind"]), data["conn_id"], data.get("text", "")
        )


@dataclass(frozen=True)
class ToClient:
    """Shard -> one connection: forward this text, and follow this room from now on.

    ``follow_room`` rides along rather than travelling as its own message because the two
    are one decision — a client takes a place in a room *and* starts receiving that
    room's broadcasts — and splitting them would open a window where the place exists but
    the traffic is not being followed yet, which is a lost first delta.

    It is the shard's **key** for the room, not the short code a player types to join one:
    the gateway turns it straight into a subject. Naming it after the room a player sees
    would invite someone to show it to them.

    It is set for **anyone** given a place — the two players and every spectator alike.
    The gateway cannot tell them apart and has no reason to: a watcher is a subscriber,
    and only the shard knows that this one may not also send moves.

    There is no matching "stop": a client stops following a room when its socket closes,
    and nothing in the game lets someone walk out of a room without doing that.

    ``claim`` is the same idea applied to the connection itself: *send this one's
    messages to me from now on*. A shard sets it when it first answers a connection, and
    again when it seats one another shard was holding — which is the only way ownership
    ever moves. The gateway obeys it without knowing what a shard is for, exactly as it
    follows a room without knowing what a room is.

    ``text`` may be **empty**, and that is not a degenerate case: it is how a shard says
    "you are mine" about a connection that has nothing to be told yet. The gateway sends
    nothing to the socket when it is.
    """

    text: str
    follow_room: Optional[str] = None
    claim: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "follow_room": self.follow_room,
            "claim": self.claim,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ToClient":
        return cls(data["text"], data.get("follow_room"), data.get("claim"))


# The two envelopes are told apart by the subject they arrive on, never by sniffing their
# contents: a ClientEvent only ever travels on `lobby.cmd`, and a ToClient only ever on a
# `conn.{gateway}.{connection}` mailbox. Hence two decoders and one encoder.


@dataclass(frozen=True)
class Seatee:
    """One player being handed to the shard that will run her game.

    Everything that shard needs and has no way to look up: which connection she is on,
    who she is, and what she is rated. It may never have spoken to her — that is the
    point — so asking it to find any of this out would be a database round trip for
    something the matchmaking queue was already sorted by.
    """

    conn_id: str
    username: str
    rating: int

    def to_dict(self) -> dict:
        return {
            "conn_id": self.conn_id,
            "username": self.username,
            "rating": self.rating,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Seatee":
        return cls(data["conn_id"], data["username"], data["rating"])


@dataclass(frozen=True)
class StartGame:
    """Shard -> shard: run a game between these two, whoever was holding them.

    The one message that moves work rather than reporting it. It is addressed to a shard
    the allocator chose, and the pair inside it may be sitting on two different gateways
    and have been claimed by two different shards a moment ago. The receiver does not
    care and does not ask: it makes a game, seats them both, and claims their connections
    on the way past.
    """

    white: Seatee
    black: Seatee

    def to_dict(self) -> dict:
        return {"white": self.white.to_dict(), "black": self.black.to_dict()}

    @classmethod
    def from_dict(cls, data: dict) -> "StartGame":
        return cls(Seatee.from_dict(data["white"]), Seatee.from_dict(data["black"]))


@dataclass(frozen=True)
class JoinGame:
    """Shard -> shard: put this one into the game behind ``room_id``, which you run.

    The other half of :class:`StartGame`, and the reason a private room id can be typed
    into any client on any machine: the room is claimed globally, so whoever the joiner
    happens to be talking to can find out where it is and send her there. She may end up
    black, or she may end up watching — that is the receiving shard's to decide, and it
    decides it exactly as it would for somebody who had been there all along.
    """

    joiner: Seatee
    room_id: str

    def to_dict(self) -> dict:
        return {"joiner": self.joiner.to_dict(), "room_id": self.room_id}

    @classmethod
    def from_dict(cls, data: dict) -> "JoinGame":
        return cls(Seatee.from_dict(data["joiner"]), data["room_id"])


def encode(envelope) -> str:
    """Pack an envelope into the JSON string that goes on the wire."""
    return json.dumps(envelope.to_dict())


def decode_client_event(payload: str) -> ClientEvent:
    """Read a :class:`ClientEvent` off ``lobby.cmd``."""
    return ClientEvent.from_dict(json.loads(payload))


def decode_to_client(payload: str) -> ToClient:
    """Read a :class:`ToClient` off a connection's mailbox."""
    return ToClient.from_dict(json.loads(payload))


def decode_start_game(payload: str) -> StartGame:
    """Read a :class:`StartGame` off a shard's own start-game subject."""
    return StartGame.from_dict(json.loads(payload))


def decode_join_game(payload: str) -> JoinGame:
    """Read a :class:`JoinGame` off a shard's own join-game subject."""
    return JoinGame.from_dict(json.loads(payload))
