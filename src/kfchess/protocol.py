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
from enum import Enum
from typing import ClassVar, Optional

from kfchess.model.color import Color
from kfchess.snapshot import GameSnapshot

# --- Message type tags -------------------------------------------------------
class MessageType(str, Enum):
    """Every wire message's ``type`` tag, in one place.

    Subclassing ``str`` keeps the wire format unchanged: each member *is* its lowercase
    string (``MessageType.MOVE == "move"``), so ``json.dumps`` writes the plain tag and a
    plain string decoded from JSON matches the enum member on lookup. Code gains a single,
    typo-proof vocabulary with editor completion instead of scattered string literals.
    """

    MOVE = "move"                # client -> server: a move command such as "WQe2e5"
    LOGIN = "login"              # client -> server: this client's username + password
    STATE = "state"              # server -> client: the current game snapshot
    ASSIGNED = "assigned"        # server -> client: which colour this client plays
    WELCOME = "welcome"          # server -> client: login accepted; your colour + rating
    REJECTED = "rejected"        # server -> client: a move (or login) was refused, w/ reason
    EVENT = "event"              # server -> client: a one-shot notification (e.g. a sound)
    PLAY = "play"                # client -> server: put me in the matchmaking queue ("Play")
    SEATED = "seated"            # server -> client: you are now seated in a game as a colour
    NOTICE = "notice"            # server -> client: a lobby-level notice (e.g. "no_opponent")
    CREATE_ROOM = "create_room"  # client -> server: open a new private room, I'm white
    JOIN_ROOM = "join_room"      # client -> server: join the room with this id


@dataclass(frozen=True)
class Move:
    """Client -> server: play the move described by ``cmd`` (e.g. ``"WQe2e5"``)."""

    type: ClassVar[MessageType] = MessageType.MOVE
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

    type: ClassVar[MessageType] = MessageType.LOGIN
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

    type: ClassVar[MessageType] = MessageType.WELCOME
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

    type: ClassVar[MessageType] = MessageType.STATE
    snapshot: GameSnapshot

    def to_dict(self) -> dict:
        return {"type": self.type, "snapshot": self.snapshot.to_dict()}

    @classmethod
    def from_dict(cls, data: dict) -> "State":
        return cls(GameSnapshot.from_dict(data["snapshot"]))


@dataclass(frozen=True)
class Assigned:
    """Server -> client: this client plays ``color``."""

    type: ClassVar[MessageType] = MessageType.ASSIGNED
    color: Color

    def to_dict(self) -> dict:
        return {"type": self.type, "color": self.color.value}

    @classmethod
    def from_dict(cls, data: dict) -> "Assigned":
        return cls(Color(data["color"]))


@dataclass(frozen=True)
class Rejected:
    """Server -> client: the last move was refused; ``reason`` says why."""

    type: ClassVar[MessageType] = MessageType.REJECTED
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

    type: ClassVar[MessageType] = MessageType.EVENT
    kind: str

    def to_dict(self) -> dict:
        return {"type": self.type, "kind": self.kind}

    @classmethod
    def from_dict(cls, data: dict) -> "Event":
        return cls(data["kind"])


@dataclass(frozen=True)
class Play:
    """Client -> server: put this (already logged-in) client into matchmaking.

    Carries nothing — the server already knows who is asking and at what rating. It is
    the shell lobby's "Play" (regular) choice; the "Rooms" choice uses other messages.
    """

    type: ClassVar[MessageType] = MessageType.PLAY

    def to_dict(self) -> dict:
        return {"type": self.type}

    @classmethod
    def from_dict(cls, data: dict) -> "Play":
        return cls()


@dataclass(frozen=True)
class Seated:
    """Server -> client: you have been placed in a game as ``color``.

    Sent when matchmaking or a room seats the player — separately from :class:`Welcome`,
    which now only confirms login and leaves the client in the lobby. ``color`` is
    ``None`` for a spectator (a room's third-and-later joiners). ``room_id`` is the
    private room's id when seated via a room, or ``None`` for a matchmade game.
    """

    type: ClassVar[MessageType] = MessageType.SEATED
    color: Optional[Color]
    room_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "color": None if self.color is None else self.color.value,
            "room_id": self.room_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Seated":
        color = None if data["color"] is None else Color(data["color"])
        return cls(color, data.get("room_id"))


@dataclass(frozen=True)
class CreateRoom:
    """Client -> server: open a new private room; the creator plays white."""

    type: ClassVar[MessageType] = MessageType.CREATE_ROOM

    def to_dict(self) -> dict:
        return {"type": self.type}

    @classmethod
    def from_dict(cls, data: dict) -> "CreateRoom":
        return cls()


@dataclass(frozen=True)
class JoinRoom:
    """Client -> server: join the room identified by ``room_id``.

    The second joiner plays black; anyone after that watches as a spectator. An unknown
    id comes back as a :class:`Notice` (``"no_such_room"``).
    """

    type: ClassVar[MessageType] = MessageType.JOIN_ROOM
    room_id: str

    def to_dict(self) -> dict:
        return {"type": self.type, "room_id": self.room_id}

    @classmethod
    def from_dict(cls, data: dict) -> "JoinRoom":
        return cls(data["room_id"])


@dataclass(frozen=True)
class Notice:
    """Server -> client: a lobby-level notice, identified by a short ``reason`` code.

    Used for things that are neither game state nor a rejected action — chiefly
    ``"no_opponent"`` when a matchmaking search times out, which the client turns into a
    "can't find opponent" popup.
    """

    type: ClassVar[MessageType] = MessageType.NOTICE
    reason: str

    def to_dict(self) -> dict:
        return {"type": self.type, "reason": self.reason}

    @classmethod
    def from_dict(cls, data: dict) -> "Notice":
        return cls(data["reason"])


# Dispatch table: message tag -> the class that reads it. Keyed by the enum members,
# but a plain string decoded from JSON still finds its class because each member *is*
# its string (str-equality/hash), so ``_BY_TYPE["move"]`` and ``_BY_TYPE[MessageType.MOVE]``
# are the same lookup.
_BY_TYPE = {
    MessageType.MOVE: Move,
    MessageType.LOGIN: Login,
    MessageType.STATE: State,
    MessageType.ASSIGNED: Assigned,
    MessageType.WELCOME: Welcome,
    MessageType.REJECTED: Rejected,
    MessageType.EVENT: Event,
    MessageType.PLAY: Play,
    MessageType.SEATED: Seated,
    MessageType.NOTICE: Notice,
    MessageType.CREATE_ROOM: CreateRoom,
    MessageType.JOIN_ROOM: JoinRoom,
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
