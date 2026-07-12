"""Promotion: the arrival effect that turns a pawn into a queen.

When a pawn *arrives* on the far row (white -> row 0, black -> the last row) it is
promoted. This is a pluggable "on-reach-special-square" arrival effect (per the
design), applied by the arbiter when a piece lands — it is not part of move
legality. The promoted-to type and the pawns' forward directions are injected, so
the policy is data-driven rather than hardcoded, and the promotion target is
parameterizable (default: queen).
"""

from __future__ import annotations

from typing import Mapping

from kfchess.model.board import Board
from kfchess.model.color import Color
from kfchess.model.piece import Piece
from kfchess.model.piece_type import PieceType
from kfchess.model.position import Position


class Promotion:
    """Promotes a pawn that has reached its far row to ``promoted_type``."""

    def __init__(
        self, forward_by_color: Mapping[Color, int], promoted_type: PieceType
    ) -> None:
        self._forward = dict(forward_by_color)
        self._promoted_type = promoted_type

    def apply(self, piece: Piece, position: Position, board: Board) -> None:
        """Promote ``piece`` in place if it is a pawn that reached its far row."""
        if not piece.piece_type.is_pawn:
            return
        forward = self._forward[piece.color]
        far_row = 0 if forward < 0 else board.rows - 1
        if position.row == far_row:
            piece.piece_type = self._promoted_type
