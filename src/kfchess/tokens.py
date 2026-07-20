"""Piece tokens and the token-based board loader.

A *token* is the two-character name for a piece, like ``"wK"`` (white king): a colour
prefix (``w``/``b``) plus the piece-type letter — the same string the text printer
composes and the sprite folders are named by. This module owns that vocabulary and the
CSV starting-position loader built on it.

It lives at the package root, and imports only the model, because it is pure string and
file work shared by the text layer, the graphics layer, and the networked server — it
must not sit in a graphics module that pulls in OpenCV, or a headless server could not
load a board.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from kfchess.model.board import Board
from kfchess.model.color import Color
from kfchess.model.piece import Piece
from kfchess.model.piece_type import PieceTypeRegistry, standard_piece_types

PathLike = Union[str, Path]


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


def load_board_csv(
    path: PathLike, piece_types: Optional[PieceTypeRegistry] = None
) -> Board:
    """Build a core :class:`Board` from a ``board.csv`` file.

    Each line is one board row of comma-separated cell tokens; an empty field is an
    empty cell. Truly blank lines (e.g. a trailing newline) are skipped, but a row of
    all-empty cells (``,,,,,,,``) is a real empty row and is kept.
    """
    piece_types = piece_types or standard_piece_types()
    grid = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip() and "," not in line:
            continue  # a genuinely blank line, not an empty board row
        row = [token_to_piece(cell, piece_types) for cell in line.split(",")]
        grid.append(row)
    return Board.from_grid(grid)
