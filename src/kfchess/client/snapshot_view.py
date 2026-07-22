"""Turn a received GameSnapshot into the inputs the existing renderer already draws.

The thin client owns no engine — only the latest snapshot from the server. Rather than
write a second renderer, this rebuilds the handful of objects
:meth:`BoardRenderer.render` expects (a :class:`Board` of settled pieces, the in-flight
:class:`MovingPiece` overlay, and the cooldown fractions) straight from the snapshot,
plus a :class:`SnapshotHudSource` the HUD reads scores and logs from. So the same
drawing code serves both the local game and the networked client.

Note: pieces are rebuilt fresh each frame, so per-piece sprite animation (idle/cooldown
cycling) does not advance across frames; smooth *motion* still works (it is driven by
the moving pieces' fractional positions) and so does the cooldown gauge (a fraction).
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from kfchess.model.board import Board
from kfchess.model.color import Color
from kfchess.model.piece import Piece, PieceState
from kfchess.model.piece_type import PieceTypeRegistry, standard_piece_types
from kfchess.model.position import Position
from kfchess.render_model import MovingPiece
from kfchess.snapshot import GameSnapshot
from kfchess.tokens import token_to_piece

RenderInputs = Tuple[Board, List[MovingPiece], Dict[Piece, float]]


def to_render_inputs(
    snapshot: GameSnapshot, piece_types: Optional[PieceTypeRegistry] = None
) -> RenderInputs:
    """Rebuild ``(board, moving_pieces, cooldowns)`` for the renderer from a snapshot."""
    piece_types = piece_types or standard_piece_types()
    cooldowns: Dict[Piece, float] = {}
    grid: List[List[Optional[Piece]]] = []
    for row in snapshot.cells:
        grid_row: List[Optional[Piece]] = []
        for cell in row:
            if cell is None:
                grid_row.append(None)
                continue
            piece = token_to_piece(cell.token, piece_types)
            piece.state = PieceState[cell.state]
            if piece.state is PieceState.COOLDOWN:
                cooldowns[piece] = cell.cooldown
            grid_row.append(piece)
        grid.append(grid_row)

    moving = [
        MovingPiece(
            _moving_piece(view.token, piece_types),
            (view.row, view.col),
            Position(0, 0),  # source/target are unused when drawing the overlay
            Position(0, 0),
        )
        for view in snapshot.moving
    ]
    return Board.from_grid(grid), moving, cooldowns


def _moving_piece(token: str, piece_types: PieceTypeRegistry) -> Piece:
    piece = token_to_piece(token, piece_types)
    piece.state = PieceState.MOVING
    return piece


class SnapshotHudSource:
    """Serves scores and move-log lines to the HUD, read from the current snapshot.

    The HUD calls ``score(color)`` and ``recent(color, count)`` — the same methods the
    live ScoreBoard and MovesLog expose — so one of these can stand in for both. The
    frame loop calls :meth:`update` with each new snapshot before drawing.
    """

    def __init__(self) -> None:
        self._snapshot: Optional[GameSnapshot] = None

    def update(self, snapshot: Optional[GameSnapshot]) -> None:
        """Point the HUD at the latest snapshot (``None`` before the first arrives)."""
        self._snapshot = snapshot

    def score(self, color: Color) -> int:
        if self._snapshot is None:
            return 0
        return self._snapshot.scores.get(color, 0)

    def recent(self, color: Color, count: int) -> List[str]:
        if self._snapshot is None:
            return []
        return self._snapshot.logs.get(color, [])[-count:]

    def name(self, color: Color) -> Optional[str]:
        """The player's chosen name for ``color``, or ``None`` if not logged in yet.

        ``None`` lets the HUD fall back to its default label until a Login arrives.
        """
        if self._snapshot is None:
            return None
        return self._snapshot.names.get(color)
