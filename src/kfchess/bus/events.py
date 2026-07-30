"""The event objects carried on the :class:`EventBus`.

Each event is a small, immutable record of *what happened* — the payload a subscriber
receives. Every event knows its own ``topic`` (a class-level constant, not an init
field), so :meth:`EventBus.publish` can route it without the caller repeating the
channel name. Events hold only model values (pieces, positions, colours); they carry
no rendering, timing, or network concerns.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Optional

from kfchess.bus import topics
from kfchess.model.color import Color
from kfchess.model.piece import Piece
from kfchess.model.position import Position


@dataclass(frozen=True)
class MoveStarted:
    """A piece has begun moving from ``source`` toward ``target``.

    ``start_ms``/``arrival_ms`` are when it left and when it is due. Subscribers that
    only care *that* a move happened (the log, the banner, sound) ignore them; the one
    that puts the event on a wire needs them, because they are what lets the far side
    draw the piece in flight without being sent the board.
    """

    topic: ClassVar[str] = topics.MOVE_STARTED
    piece: Piece
    source: Position
    target: Position
    start_ms: int = 0
    arrival_ms: int = 0


@dataclass(frozen=True)
class Settled:
    """``piece`` has come to rest on ``cell``, on cooldown for ``cooldown_ms``."""

    topic: ClassVar[str] = topics.SETTLED
    piece: Piece
    cell: Position
    at_ms: int = 0
    cooldown_ms: int = 0


@dataclass(frozen=True)
class Captured:
    """``victim`` has just been captured and removed from the board."""

    topic: ClassVar[str] = topics.CAPTURE
    victim: Piece
    at_ms: int = 0


@dataclass(frozen=True)
class CooldownDone:
    """``piece``'s landing cooldown has elapsed; it may move again."""

    topic: ClassVar[str] = topics.COOLDOWN_DONE
    piece: Piece
    at_ms: int = 0


@dataclass(frozen=True)
class GameStarted:
    """A fresh game has begun (published once, when the game is set up)."""

    topic: ClassVar[str] = topics.GAME_STARTED


@dataclass(frozen=True)
class GameOver:
    """A king was captured; the game has ended. ``winner`` is the victorious side."""

    topic: ClassVar[str] = topics.GAME_OVER
    winner: Optional[Color] = None
