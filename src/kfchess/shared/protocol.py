"""Protocol: the message vocabulary the client and server speak over the wire.

Where :mod:`kfchess.snapshot` is the shared *language* (a picture of the game), this is
the *grammar*: the small set of message types the two sides exchange, and how each is
packed into a JSON string (:func:`encode`) and read back into a typed object
(:func:`decode`). Every message carries a ``type`` tag — the same self-describing
pattern the bus events use with ``topic`` — so the receiver can dispatch on it.

Server -> client traffic comes in two families. :class:`State` is the whole picture, now
sent only where a whole picture is needed: when a player is seated, when one reconnects,
and as a periodic resync (``config.SNAPSHOT_RESYNC_MS``). Everything else is a **delta**
— :class:`MoveStarted`, :class:`Settled`, :class:`Captured`, :class:`CooldownDone`,
:class:`GameOver`, :class:`Disconnected`, :class:`Reconnected` — sent once, when the
thing happens. See the section comment above them for why.

It lives in :mod:`kfchess.shared`, beside ``snapshot``, because it is the vocabulary the
server and the client both depend on. It imports only ``json``, the snapshot, and
``Color``, so it stays free of the engine, the graphics, and the actual socket library.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import ClassVar, Dict, Optional

from kfchess.model.color import Color
from kfchess.shared.codes import NoticeReason, RejectReason, WireEnum
from kfchess.shared.snapshot import GameSnapshot

# --- Message type tags -------------------------------------------------------
class MessageType(WireEnum):
    """Every wire message's ``type`` tag, in one place.

    Subclassing ``str`` (via :class:`WireEnum`) keeps the wire format unchanged: each
    member *is* its lowercase string (``MessageType.MOVE == "move"``), so ``json.dumps``
    writes the plain tag and a plain string decoded from JSON matches the enum member on
    lookup. Code gains a single, typo-proof vocabulary with editor completion instead of
    scattered string literals.
    """

    MOVE = "move"                # client -> server: a move command such as "WQe2e5"
    LOGIN = "login"              # client -> server: this client's username + password
    STATE = "state"              # server -> client: the current game snapshot
    WELCOME = "welcome"          # server -> client: login accepted; your colour + rating
    REJECTED = "rejected"        # server -> client: a move (or login) was refused, w/ reason
    EVENT = "event"              # server -> client: a one-shot notification (e.g. a sound)
    PLAY = "play"                # client -> server: put me in the matchmaking queue ("Play")
    SEATED = "seated"            # server -> client: you are now seated in a game as a colour
    NOTICE = "notice"            # server -> client: a lobby-level notice (e.g. "no_opponent")
    CREATE_ROOM = "create_room"  # client -> server: open a new private room, I'm white
    JOIN_ROOM = "join_room"      # client -> server: join the room with this id
    # --- deltas: server -> client, one per thing that actually happened -------
    MOVE_STARTED = "move_started"    # a piece left for another square
    SETTLED = "settled"              # a piece stopped somewhere and began cooling down
    CAPTURED = "captured"            # a piece left the board
    COOLDOWN_DONE = "cooldown_done"  # a piece is free to move again
    GAME_OVER = "game_over"          # a king fell (or somebody resigned)
    DISCONNECTED = "disconnected"    # a player dropped; their resign countdown started
    RECONNECTED = "reconnected"      # they came back; the countdown is cancelled


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
class Rejected:
    """Server -> client: the last move (or login) was refused; ``reason`` says why."""

    type: ClassVar[MessageType] = MessageType.REJECTED
    reason: RejectReason

    def to_dict(self) -> dict:
        return {"type": self.type, "reason": self.reason}

    @classmethod
    def from_dict(cls, data: dict) -> "Rejected":
        return cls(RejectReason(data["reason"]))


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
    :attr:`~kfchess.shared.codes.NoticeReason.NO_OPPONENT` when a matchmaking search
    times out, which the client turns into a "can't find opponent" popup.
    """

    type: ClassVar[MessageType] = MessageType.NOTICE
    reason: NoticeReason

    def to_dict(self) -> dict:
        return {"type": self.type, "reason": self.reason}

    @classmethod
    def from_dict(cls, data: dict) -> "Notice":
        return cls(NoticeReason(data["reason"]))


# --- Deltas: what changed, instead of what everything is -----------------------
# A full :class:`State` is ~2,148 bytes, and sending one twenty times a second to every
# client costs ~350 kbps each -- for a game where one piece moves every two seconds. The
# messages below carry only the thing that happened, and the client recomputes the rest:
# it already knows ``MS_PER_CELL`` and ``COOLDOWN_MS``, so given a move's endpoints and
# times it can interpolate every frame in between exactly as ``Motion.position_at`` does
# on the server.
#
# Two conventions hold the set together:
#
# - **``piece_id``** names one piece for as long as it lives. The board cannot be the
#   name, because a piece in flight is between squares; a moving piece is identified by
#   the id it was given when its move started, and that id is what later ``Settled`` /
#   ``Captured`` / ``CooldownDone`` messages refer to. It is opaque: the client only ever
#   compares ids for equality.
# - **``at_ms``/``start_ms``/``arrival_ms``** are *server clock* times, the same
#   ``now_ms`` a snapshot carries. The client keeps its own clock in step with the last
#   snapshot it saw, so every delta lands on the same timeline the server used.
#
# Nothing here adjudicates: the client interpolates between two points the server
# announced, which is arithmetic, not judgement. Captures, legality and game-over are
# still decided by ``GameEngine`` alone and obeyed unconditionally.


@dataclass(frozen=True)
class MoveStarted:
    """Server -> client: ``piece_id`` left ``from_sq`` for ``to_sq``.

    ``token`` (e.g. ``"wQ"``) is what to draw; the two times are when the piece left and
    when it is due, which is everything needed to place it on any frame in between.
    """

    type: ClassVar[MessageType] = MessageType.MOVE_STARTED
    piece_id: int
    token: str
    from_sq: str
    to_sq: str
    start_ms: int
    arrival_ms: int

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "piece_id": self.piece_id,
            "token": self.token,
            "from_sq": self.from_sq,
            "to_sq": self.to_sq,
            "start_ms": self.start_ms,
            "arrival_ms": self.arrival_ms,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MoveStarted":
        return cls(
            data["piece_id"],
            data["token"],
            data["from_sq"],
            data["to_sq"],
            data["start_ms"],
            data["arrival_ms"],
        )


@dataclass(frozen=True)
class Settled:
    """Server -> client: ``piece_id`` came to rest on ``at_sq`` and is now cooling down.

    Sent for every way a motion can end — arriving, being blocked short of a friend, or
    landing from a jump — so the client never has to guess which happened. ``token`` is
    re-sent because a pawn reaching the far rank settles as a different piece.
    ``cooldown_ms`` is the gauge's length; a :class:`CooldownDone` closes it.
    """

    type: ClassVar[MessageType] = MessageType.SETTLED
    piece_id: int
    token: str
    at_sq: str
    at_ms: int
    cooldown_ms: int

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "piece_id": self.piece_id,
            "token": self.token,
            "at_sq": self.at_sq,
            "at_ms": self.at_ms,
            "cooldown_ms": self.cooldown_ms,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Settled":
        return cls(
            data["piece_id"],
            data["token"],
            data["at_sq"],
            data["at_ms"],
            data["cooldown_ms"],
        )


@dataclass(frozen=True)
class Captured:
    """Server -> client: ``piece_id`` was taken and is off the board.

    No square travels with it: the client already knows where that piece was, settled or
    in flight, and a second copy of the answer could only ever disagree with the first.
    ``token`` is kept because the scoreboard and the moves log are driven by *what* fell.
    """

    type: ClassVar[MessageType] = MessageType.CAPTURED
    piece_id: int
    token: str
    at_ms: int

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "piece_id": self.piece_id,
            "token": self.token,
            "at_ms": self.at_ms,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Captured":
        return cls(data["piece_id"], data["token"], data["at_ms"])


@dataclass(frozen=True)
class CooldownDone:
    """Server -> client: ``piece_id``'s cooldown has elapsed; it may move again."""

    type: ClassVar[MessageType] = MessageType.COOLDOWN_DONE
    piece_id: int
    at_ms: int

    def to_dict(self) -> dict:
        return {"type": self.type, "piece_id": self.piece_id, "at_ms": self.at_ms}

    @classmethod
    def from_dict(cls, data: dict) -> "CooldownDone":
        return cls(data["piece_id"], data["at_ms"])


@dataclass(frozen=True)
class GameOver:
    """Server -> client: the game has ended; ``winner`` took it (``None`` = nobody).

    ``ratings`` carries both players' *new* ELO, computed by the shard the moment the
    game ended: :func:`~kfchess.server.rating.updated_ratings` is a pure function and the
    session already holds both ratings, so the player sees her new number immediately
    instead of waiting on a database write. It is empty for an unrated game (a room whose
    second seat was never filled).
    """

    type: ClassVar[MessageType] = MessageType.GAME_OVER
    winner: Optional[Color]
    at_ms: int
    ratings: Dict[Color, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "winner": None if self.winner is None else self.winner.value,
            "at_ms": self.at_ms,
            "ratings": {color.value: r for color, r in self.ratings.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GameOver":
        winner = None if data["winner"] is None else Color(data["winner"])
        ratings = {Color(prefix): r for prefix, r in data["ratings"].items()}
        return cls(winner, data["at_ms"], ratings)


@dataclass(frozen=True)
class Disconnected:
    """Server -> client: ``color``'s player dropped; they auto-resign at ``resign_at_ms``.

    One message replaces a countdown that used to be re-sent in every snapshot twenty
    times a second: the client is told the deadline once and counts down to it against
    its own clock.
    """

    type: ClassVar[MessageType] = MessageType.DISCONNECTED
    color: Color
    resign_at_ms: int

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "color": self.color.value,
            "resign_at_ms": self.resign_at_ms,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Disconnected":
        return cls(Color(data["color"]), data["resign_at_ms"])


@dataclass(frozen=True)
class Reconnected:
    """Server -> client: the missing player is back; cancel the resign countdown.

    Carries nothing — at most one seat per game is ever mid-countdown, so "the one that
    was missing" is unambiguous.
    """

    type: ClassVar[MessageType] = MessageType.RECONNECTED

    def to_dict(self) -> dict:
        return {"type": self.type}

    @classmethod
    def from_dict(cls, data: dict) -> "Reconnected":
        return cls()


# Dispatch table: message tag -> the class that reads it. Keyed by the enum members,
# but a plain string decoded from JSON still finds its class because each member *is*
# its string (str-equality/hash), so ``_BY_TYPE["move"]`` and ``_BY_TYPE[MessageType.MOVE]``
# are the same lookup.
_BY_TYPE = {
    MessageType.MOVE: Move,
    MessageType.LOGIN: Login,
    MessageType.STATE: State,
    MessageType.WELCOME: Welcome,
    MessageType.REJECTED: Rejected,
    MessageType.EVENT: Event,
    MessageType.PLAY: Play,
    MessageType.SEATED: Seated,
    MessageType.NOTICE: Notice,
    MessageType.CREATE_ROOM: CreateRoom,
    MessageType.JOIN_ROOM: JoinRoom,
    MessageType.MOVE_STARTED: MoveStarted,
    MessageType.SETTLED: Settled,
    MessageType.CAPTURED: Captured,
    MessageType.COOLDOWN_DONE: CooldownDone,
    MessageType.GAME_OVER: GameOver,
    MessageType.DISCONNECTED: Disconnected,
    MessageType.RECONNECTED: Reconnected,
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
