"""BoardRenderer: turn a core :class:`Board` into a drawn image.

The renderer is *pure output*: given the current board it composites a fresh frame —
the board background plus each piece's sprite — and returns it as an :class:`Img`. It
returns the image rather than showing it, which keeps it testable (write the frame to
a PNG and inspect it) and lets the frame loop decide when to display.

M1 draws the settled board with each piece's ``idle`` sprite. Later milestones extend
``render`` to also draw in-flight pieces at their interpolated positions (M2) and to
pick each piece's sprite by its animation state (M3).
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional, Union

from kfchess.config import SELECT_COLOR
from kfchess.engine.arbiter import MovingPiece
from kfchess.graphics.assets import AnimationBank, piece_token
from kfchess.graphics.img import Img
from kfchess.graphics.piece_view import PieceView
from kfchess.model.board import Board
from kfchess.model.piece import Piece, PieceState
from kfchess.model.position import Position

PathLike = Union[str, Path]


class BoardRenderer:
    """Composites a board image from the background and the pieces' animated sprites."""

    def __init__(
        self,
        board_image_path: PathLike,
        animation_bank: AnimationBank,
        cell_px: int,
        piece_view: Optional[PieceView] = None,
    ) -> None:
        self._board_image_path = Path(board_image_path)
        self._bank = animation_bank
        self._cell_px = cell_px
        # One PieceView for the whole game: it must remember per-piece animation
        # timing across frames, so it is created once here, not per render call.
        self._piece_view = piece_view or PieceView()
        self._background: Optional[Img] = None  # loaded+scaled once, then copied

    def render(
        self,
        board: Board,
        moving_pieces: Iterable[MovingPiece] = (),
        now_ms: int = 0,
        selected: Optional[Position] = None,
    ) -> Img:
        """A freshly drawn frame: background, settled pieces, in-flight pieces, highlight.

        Each piece is drawn with the animation frame for its current state at
        ``now_ms``. A piece in flight still occupies its *origin* cell on the board
        (the core keeps it there until it arrives), so settled drawing skips
        ``MOVING`` pieces and they are drawn instead at their interpolated position
        from ``moving_pieces`` — otherwise the same piece would appear twice. If
        ``selected`` is given, its cell is outlined last so it sits on top.
        """
        canvas = self._board_background(board).copy()
        for row in range(board.rows):
            for col in range(board.cols):
                piece = board.piece_at(Position(row, col))
                if piece is None or piece.state is PieceState.MOVING:
                    continue
                frame = self._piece_frame(piece, now_ms)
                frame.draw_on(canvas, col * self._cell_px, row * self._cell_px)
        for moving in moving_pieces:
            frame = self._piece_frame(moving.piece, now_ms)
            row_f, col_f = moving.position  # fractional (row, col)
            frame.draw_on(
                canvas, round(col_f * self._cell_px), round(row_f * self._cell_px)
            )
        if selected is not None:
            canvas.draw_rect(
                selected.col * self._cell_px,
                selected.row * self._cell_px,
                self._cell_px,
                self._cell_px,
                SELECT_COLOR,
            )
        return canvas

    def _piece_frame(self, piece: Piece, now_ms: int) -> Img:
        """The animation frame to draw for ``piece`` right now (by its state + timing)."""
        state, elapsed_ms = self._piece_view.state_and_elapsed(piece, now_ms)
        return self._bank.animation(piece_token(piece), state).frame_at(elapsed_ms)

    def _board_background(self, board: Board) -> Img:
        """The board image scaled to the board's pixel size, loaded once and cached.

        The frame loop calls ``render`` many times a second; scaling the background
        image every frame would be wasteful, so it is built on first use and then
        only *copied* per frame.
        """
        if self._background is None:
            width = board.cols * self._cell_px
            height = board.rows * self._cell_px
            self._background = Img().read(self._board_image_path, size=(width, height))
        return self._background
