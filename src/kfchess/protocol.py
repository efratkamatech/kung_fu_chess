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
from typing import ClassVar, Optional

from kfchess.model.color import Color
from kfchess.snapshot import GameSnapshot

# --- Message type tags -------------------------------------------------------
MOVE = "move"          # client -> server: a move command such as "WQe2e5"
LOGIN = "login"        # client -> server: this client's username + password
STATE = "state"        # server -> client: the current game snapshot
ASSIGNED = "assigned"  # server -> client: which colour this client plays
WELCOME = "welcome"    # server -> client: login accepted; your colour + rating
REJECTED = "rejected"  # server -> client: a move (or login) was refused, with a reason
EVENT = "event"        # server -> client: a one-shot notification (e.g. play a sound)


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
class Login:
    """Client -> server: identify this connection as ``username`` with ``password``.

    Sent right after connecting and before any move — the shell home screen collects the
    credentials, then the client sends them. Resent (same connection) after a rejected
    password so the player can try again.
    """

    type: ClassVar[str] = LOGIN
    username: str
    password: str = ""

    def to_dict(self) -> dict:
        return {"type": self.type, "username": self.username, "password": self.password}

    @classmethod
    def from_dict(cls, data: dict) -> "Login":
        return cls(data["username"], data.get("password", ""))


@dataclass(frozen=True)
class Welcome:
    """Server -> client: login accepted. Carries the assigned ``color`` and ``rating``.

    ``color`` is ``None`` for a spectator (no free seat). This is the unambiguous
    "you're in" signal the client waits for before opening the window; a bad password
    comes back as :class:`Rejected` instead.
    """

    type: ClassVar[str] = WELCOME
    color: Optional[Color]
    rating: int

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "color": None if self.color is None else self.color.value,
            "rating": self.rating,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Welcome":
        color = None if data["color"] is None else Color(data["color"])
        return cls(color, data["rating"])


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


@dataclass(frozen=True)
class Event:
    """Server -> client: something just happened; react to it once (e.g. play a sound).

    Sent *alongside* ``State``, not instead of it — the board's truth always comes from
    a snapshot. ``kind`` is one of the ``config.SOUND_*`` names (``"move"``,
    ``"capture"``, ``"game_start"``, ``"game_over"``): the same vocabulary
    :class:`kfchess.graphics.sound.SoundEffects` already plays locally, so a client's own
    sound player can act on ``kind`` directly with no further translation.
    """

    type: ClassVar[str] = EVENT
    kind: str

    def to_dict(self) -> dict:
        return {"type": self.type, "kind": self.kind}

    @classmethod
    def from_dict(cls, data: dict) -> "Event":
        return cls(data["kind"])


# Dispatch table: message tag -> the class that reads it.
_BY_TYPE = {
    MOVE: Move,
    LOGIN: Login,
    STATE: State,
    ASSIGNED: Assigned,
    WELCOME: Welcome,
    REJECTED: Rejected,
    EVENT: Event,
}


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
