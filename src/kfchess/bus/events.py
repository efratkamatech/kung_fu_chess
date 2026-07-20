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
    """A piece has begun moving from ``source`` toward ``target``."""

    topic: ClassVar[str] = topics.MOVE_STARTED
    piece: Piece
    source: Position
    target: Position


@dataclass(frozen=True)
class Captured:
    """``victim`` has just been captured and removed from the board."""

    topic: ClassVar[str] = topics.CAPTURE
    victim: Piece


@dataclass(frozen=True)
class GameStarted:
    """A fresh game has begun (published once, when the game is set up)."""

    topic: ClassVar[str] = topics.GAME_STARTED


@dataclass(frozen=True)
class GameOver:
    """A king was captured; the game has ended. ``winner`` is the victorious side."""

    topic: ClassVar[str] = topics.GAME_OVER
    winner: Optional[Color] = None
