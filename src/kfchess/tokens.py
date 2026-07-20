"""Piece tokens: the two-character name for a piece, like ``"wK"`` (white king).

A token is a colour prefix (``w``/``b``) plus the piece-type letter — the same string
the text printer composes and the sprite folders are named by. Kept here, at the
package root, because it is pure string work shared by the text layer, the graphics
layer, and the networked server; it must not live in a graphics module that pulls in
OpenCV, or a headless server could not use it.
"""

from __future__ import annotations

from typing import Optional

from kfchess.model.color import Color
from kfchess.model.piece import Piece
from kfchess.model.piece_type import PieceTypeRegistry


def piece_token(piece: Piece) -> str:
    """The token/folder name for a piece — a white king is ``"wK"``.

    This is the same composition the text printer uses, so a piece's token and its
    sprite folder name are guaranteed to agree.
    """
    return f"{piece.color.prefix}{piece.piece_type.letter}"


def token_to_piece(token: str, piece_types: PieceTypeRegistry) -> Optional[Piece]:
    """Turn a token into a :class:`Piece`, or ``None`` for an empty cell.

    ``"wK"`` -> a white king; ``""`` (or whitespace) -> an empty cell. Reuses the
    core's own colour/type resolution, so an unknown token raises the same
    ``ValueError``/``KeyError`` the text parser would surface.
    """
    token = token.strip()
    if not token:
        return None
    color = Color.from_prefix(token[0])
    piece_type = piece_types.get(token[1:])
    return Piece(piece_type, color)
