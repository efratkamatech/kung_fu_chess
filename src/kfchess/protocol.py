"""Protocol: the message vocabulary the client and server speak over the wire.

Where :mod:`kfchess.snapshot` is the shared *language* (a picture of the game), this is
the *grammar*: the small set of message types the two sides exchange, and how each is
packed into a JSON string (:func:`encode`) and read back into a typed object
(:func:`decode`). Every message carries a ``type`` tag — the same self-describing
pattern the bus events use with ``topic`` — so the receiver can dispatch on it.

It lives at the package root, beside ``snapshot``, because both the server and the
client depend on it. It imports only ``json``, the snapshot, and ``Color``, so it stays
free of the engine, the graphics, and the actual socket library.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import ClassVar

from kfchess.model.color import Color
from kfchess.snapshot import GameSnapshot

# --- Message type tags -------------------------------------------------------
MOVE = "move"          # client -> server: a move command such as "WQe2e5"
STATE = "state"        # server -> client: the current game snapshot
ASSIGNED = "assigned"  # server -> client: which colour this client plays
REJECTED = "rejected"  # server -> client: a move was refused, with a reason


@dataclass(frozen=True)
class Move:
    """Client -> server: play the move described by ``cmd`` (e.g. ``"WQe2e5"``)."""

    type: ClassVar[str] = MOVE
    cmd: str

    def to_dict(self) -> dict:
        return {"type": self.type, "cmd": self.cmd}

    @classmethod
    def from_dict(cls, data: dict) -> "Move":
        return cls(data["cmd"])


@dataclass(frozen=True)
class State:
    """Server -> client: the whole game right now, as a snapshot."""

    type: ClassVar[str] = STATE
    snapshot: GameSnapshot

    def to_dict(self) -> dict:
        return {"type": self.type, "snapshot": self.snapshot.to_dict()}

    @classmethod
    def from_dict(cls, data: dict) -> "State":
        return cls(GameSnapshot.from_dict(data["snapshot"]))


@dataclass(frozen=True)
class Assigned:
    """Server -> client: this client plays ``color``."""

    type: ClassVar[str] = ASSIGNED
    color: Color

    def to_dict(self) -> dict:
        return {"type": self.type, "color": self.color.value}

    @classmethod
    def from_dict(cls, data: dict) -> "Assigned":
        return cls(Color(data["color"]))


@dataclass(frozen=True)
class Rejected:
    """Server -> client: the last move was refused; ``reason`` says why."""

    type: ClassVar[str] = REJECTED
    reason: str

    def to_dict(self) -> dict:
        return {"type": self.type, "reason": self.reason}

    @classmethod
    def from_dict(cls, data: dict) -> "Rejected":
        return cls(data["reason"])


# Dispatch table: message tag -> the class that reads it.
_BY_TYPE = {MOVE: Move, STATE: State, ASSIGNED: Assigned, REJECTED: Rejected}


class ProtocolError(ValueError):
    """A wire message that does not follow the protocol (missing/unknown type)."""


def encode(message) -> str:
    """Pack a message object into a JSON string ready to send over the wire."""
    return json.dumps(message.to_dict())

def decode(text: str):
    """Read a JSON wire string back into its typed message object.

    Raises :class:`ProtocolError` if the ``type`` tag is missing or unrecognised.
    """
    data = json.loads(text)
    message_type = data.get("type")
    if message_type not in _BY_TYPE:
        raise ProtocolError(f"unknown message type: {message_type!r}")
    return _BY_TYPE[message_type].from_dict(data)
