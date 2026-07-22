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
from typing import Dict, Iterable, Optional, Union

from kfchess.config import (
    COOLDOWN_ALPHA,
    COOLDOWN_COLOR,
    GAMEOVER_ALPHA,
    GAMEOVER_BG,
    GAMEOVER_TEXT_COLOR,
    INVALID_MOVE_COLOR,
    LEGAL_MOVE_ALPHA,
    LEGAL_MOVE_COLOR,
    PANEL_BG,
    SELECT_COLOR,
    STARTBANNER_ALPHA,
    STATE_IDLE,
)
from kfchess.render_model import MovingPiece
from kfchess.graphics.assets import AnimationBank
from kfchess.graphics.geometry import board_pixel_size
from kfchess.graphics.hud import Hud
from kfchess.graphics.img import Img
from kfchess.graphics.piece_view import PieceView
from kfchess.model.board import Board
from kfchess.model.piece import Piece, PieceState
from kfchess.model.position import Position
from kfchess.tokens import piece_token

PathLike = Union[str, Path]


class BoardRenderer:
    """Composites a frame: the board with animated sprites, plus an optional HUD panel."""

    def __init__(
        self,
        board_image_path: PathLike,
        animation_bank: AnimationBank,
        cell_px: int,
        piece_view: Optional[PieceView] = None,
        huds: Iterable[Hud] = (),
        left_panel_px: int = 0,
        right_panel_px: int = 0,
    ) -> None:
        self._board_image_path = Path(board_image_path)
        self._bank = animation_bank
        self._cell_px = cell_px
        # One PieceView for the whole game: it must remember per-piece animation
        # timing across frames, so it is created once here, not per render call.
        self._piece_view = piece_view or PieceView()
        self._huds = tuple(huds)  # one panel per player (drawn at their own x)
        self._left_px = left_panel_px  # left panel width = the board's x offset
        self._right_px = right_panel_px
        self._background: Optional[Img] = None  # loaded+scaled once, then copied

    def render(
        self,
        board: Board,
        moving_pieces: Iterable[MovingPiece] = (),
        now_ms: int = 0,
        selected: Optional[Position] = None,
        cooldowns: Optional[Dict[Piece, float]] = None,
        legal_targets: Iterable[Position] = (),
        invalid_cell: Optional[Position] = None,
    ) -> Img:
        """A freshly drawn frame: background, move hints, pieces, and overlays.

        Each piece is drawn with the animation frame for its current state at
        ``now_ms``. A piece in flight still occupies its *origin* cell on the board
        (the core keeps it there until it arrives), so settled drawing skips
        ``MOVING`` pieces and they are drawn instead at their interpolated position
        from ``moving_pieces``. ``legal_targets`` are tinted green under the pieces;
        ``selected`` is outlined green and ``invalid_cell`` outlined red, on top.
        """
        canvas = self._new_canvas(board)
        for cell in legal_targets:  # green hints go under the pieces
            self._fill_cell(canvas, cell, LEGAL_MOVE_COLOR, LEGAL_MOVE_ALPHA)
        for row in range(board.rows):
            for col in range(board.cols):
                piece = board.piece_at(Position(row, col))
                if piece is None or piece.state is PieceState.MOVING:
                    continue
                state, elapsed_ms = self._piece_view.state_and_elapsed(piece, now_ms)
                frame = self._animation_frame(piece, state, elapsed_ms)
                frame.draw_on(canvas, self._cell_x(col), self._cell_y(row))
                if piece.state is PieceState.COOLDOWN and cooldowns:
                    self._draw_cooldown(canvas, row, col, cooldowns.get(piece, 0.0))
        for moving in moving_pieces:
            frame = self._piece_frame(moving.piece, now_ms)
            row_f, col_f = moving.position  # fractional (row, col)
            frame.draw_on(
                canvas,
                round(col_f * self._cell_px) + self._left_px,
                round(row_f * self._cell_px),
            )
        if selected is not None:
            canvas.draw_rect(
                self._cell_x(selected.col),
                self._cell_y(selected.row),
                self._cell_px,
                self._cell_px,
                SELECT_COLOR,
            )
        if invalid_cell is not None:
            canvas.draw_rect(
                self._cell_x(invalid_cell.col),
                self._cell_y(invalid_cell.row),
                self._cell_px,
                self._cell_px,
                INVALID_MOVE_COLOR,
            )
        for hud in self._huds:
            hud.draw(canvas)
        return canvas

    def _fill_cell(self, canvas: Img, cell: Position, color, alpha: float) -> None:
        """Blend a translucent ``color`` over the whole of ``cell`` (a move hint)."""
        canvas.fill_rect(
            self._cell_x(cell.col), self._cell_y(cell.row), self._cell_px, self._cell_px,
            color, alpha,
        )

    def draw_game_over(self, canvas: Img, title: str, subtitle: str) -> None:
        """Dim the board area and centre a game-over ``title`` + ``subtitle`` on it."""
        self._draw_banner(canvas, title, subtitle, GAMEOVER_ALPHA)

    def draw_start_banner(self, canvas: Img, title: str, subtitle: str) -> None:
        """Lightly dim the board area and centre a start ``title`` + ``subtitle``."""
        self._draw_banner(canvas, title, subtitle, STARTBANNER_ALPHA)

    def _draw_banner(
        self, canvas: Img, title: str, subtitle: str, alpha: float
    ) -> None:
        """Dim the board area by ``alpha`` and centre a ``title`` + ``subtitle`` on it."""
        board_w = canvas.width - self._left_px - self._right_px
        canvas.fill_rect(self._left_px, 0, board_w, canvas.height, GAMEOVER_BG, alpha)
        center_x = self._left_px + board_w // 2
        middle_y = canvas.height // 2
        canvas.put_text_centered(title, center_x, middle_y, 1.6, GAMEOVER_TEXT_COLOR, 3)
        canvas.put_text_centered(
            subtitle, center_x, middle_y + 60, 0.7, GAMEOVER_TEXT_COLOR, 2
        )

    def _cell_x(self, col: int) -> int:
        """Left pixel of board column ``col`` on the canvas (past the left panel)."""
        return col * self._cell_px + self._left_px

    def _cell_y(self, row: int) -> int:
        """Top pixel of board row ``row`` on the canvas."""
        return row * self._cell_px

    def _new_canvas(self, board: Board) -> Img:
        """A fresh frame canvas: side panels (if any) with the board between them."""
        board_bg = self._board_background(board)
        if self._left_px <= 0 and self._right_px <= 0:
            return board_bg.copy()
        board_w, board_h = board_pixel_size(board, self._cell_px)
        canvas = Img.blank(
            self._left_px + board_w + self._right_px, board_h, channels=3, color=PANEL_BG
        )
        board_bg.draw_on(canvas, self._left_px, 0)
        return canvas

    def _piece_frame(self, piece: Piece, now_ms: int) -> Img:
        """The animation frame to draw for ``piece`` right now (by its state + timing)."""
        state, elapsed_ms = self._piece_view.state_and_elapsed(piece, now_ms)
        return self._animation_frame(piece, state, elapsed_ms)

    def _animation_frame(self, piece: Piece, state: str, elapsed_ms: int) -> Img:
        """Pick the frame for ``piece`` in ``state``; idle is a still pose (frame 0)."""
        if state == STATE_IDLE:
            elapsed_ms = 0  # idle should not move — hold the first frame
        return self._bank.animation(piece_token(piece), state).frame_at(elapsed_ms)

    def _draw_cooldown(self, canvas: Img, row: int, col: int, remaining: float) -> None:
        """Draw the draining yellow cooldown gauge over a just-moved piece's cell.

        ``remaining`` is the cooldown's remaining fraction (1.0 -> 0.0). The fill's
        height tracks it, anchored at the bottom of the cell, so its top edge descends
        as the cooldown runs out.
        """
        if remaining <= 0.0:
            return
        height = int(remaining * self._cell_px)
        x = self._cell_x(col)
        y = self._cell_y(row) + (self._cell_px - height)
        canvas.fill_rect(x, y, self._cell_px, height, COOLDOWN_COLOR, COOLDOWN_ALPHA)

    def _board_background(self, board: Board) -> Img:
        """The board image scaled to the board's pixel size, loaded once and cached.

        The frame loop calls ``render`` many times a second; scaling the background
        image every frame would be wasteful, so it is built on first use and then
        only *copied* per frame.
        """
        if self._background is None:
            width, height = board_pixel_size(board, self._cell_px)
            self._background = Img().read(self._board_image_path, size=(width, height))
        return self._background
