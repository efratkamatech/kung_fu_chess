"""Piece and PieceState.

A ``Piece`` is a single piece on the board: its identity (type + color) and its
current lifecycle ``state``. Unlike the value objects (Position, Color, PieceType),
a Piece is *stateful* — its state changes as the game runs — so it is a plain,
mutable class compared by identity: two distinct white pawns are different pieces
even though they share a type and color.

A Piece does **not** store its own position. The Board is the single source of
truth for where each piece sits (design: "Board owns positions"), which avoids
two places disagreeing about a piece's location. A Piece also holds no text-format
knowledge; the printer composes the ``wK`` token from the piece's color and type.
"""

from __future__ import annotations

from enum import Enum, auto

from kfchess.model.color import Color
from kfchess.model.piece_type import PieceType


class PieceState(Enum):
    """A piece's lifecycle state.

    ``IDLE`` = settled; ``MOVING`` = in flight between two cells (Iteration 6). The
    remaining design states are added when their iteration introduces them:
    ``JUMPING`` (Iteration 11), and ``CAPTURED`` if/when captures need to track it.
    """

    IDLE = auto()
    MOVING = auto()


class Piece:
    """A piece on the board: identity plus current state. Compared by identity."""

    __slots__ = ("piece_type", "color", "state")

    def __init__(
        self,
        piece_type: PieceType,
        color: Color,
        state: PieceState = PieceState.IDLE,
    ) -> None:
        self.piece_type = piece_type
        self.color = color
        self.state = state

    def __repr__(self) -> str:
        return (
            f"Piece({self.piece_type.letter!r}, {self.color.name}, "
            f"{self.state.name})"
        )
