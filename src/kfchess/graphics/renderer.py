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
from typing import Optional, Union

from kfchess.config import STATE_IDLE
from kfchess.graphics.assets import SpriteBank, piece_token
from kfchess.graphics.img import Img
from kfchess.model.board import Board
from kfchess.model.position import Position

PathLike = Union[str, Path]


class BoardRenderer:
    """Composites a board image from the background and the pieces' sprites."""

    def __init__(
        self, board_image_path: PathLike, sprite_bank: SpriteBank, cell_px: int
    ) -> None:
        self._board_image_path = Path(board_image_path)
        self._bank = sprite_bank
        self._cell_px = cell_px
        self._background: Optional[Img] = None  # loaded+scaled once, then copied

    def render(self, board: Board) -> Img:
        """A freshly drawn frame of ``board`` (background + every settled piece)."""
        canvas = self._board_background(board).copy()
        for row in range(board.rows):
            for col in range(board.cols):
                piece = board.piece_at(Position(row, col))
                if piece is None:
                    continue
                sprite = self._bank.sprite(piece_token(piece), STATE_IDLE)
                sprite.draw_on(canvas, col * self._cell_px, row * self._cell_px)
        return canvas

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
