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
    """The three things a gateway ever reports about a connection."""

    CONNECTED = "connected"        # a socket opened; nothing has been said on it yet
    MESSAGE = "message"            # the client sent this text
    DISCONNECTED = "disconnected"  # the socket closed, cleanly or otherwise


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
    """

    text: str
    follow_room: Optional[str] = None

    def to_dict(self) -> dict:
        return {"text": self.text, "follow_room": self.follow_room}

    @classmethod
    def from_dict(cls, data: dict) -> "ToClient":
        return cls(data["text"], data.get("follow_room"))


# The two envelopes are told apart by the subject they arrive on, never by sniffing their
# contents: a ClientEvent only ever travels on `lobby.cmd`, and a ToClient only ever on a
# `conn.{gateway}.{connection}` mailbox. Hence two decoders and one encoder.


def encode(envelope) -> str:
    """Pack an envelope into the JSON string that goes on the wire."""
    return json.dumps(envelope.to_dict())


def decode_client_event(payload: str) -> ClientEvent:
    """Read a :class:`ClientEvent` off ``lobby.cmd``."""
    return ClientEvent.from_dict(json.loads(payload))


def decode_to_client(payload: str) -> ToClient:
    """Read a :class:`ToClient` off a connection's mailbox."""
    return ToClient.from_dict(json.loads(payload))
