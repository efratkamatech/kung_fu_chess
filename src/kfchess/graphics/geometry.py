"""Small board<->pixel geometry helpers, shared by the renderer and the wiring."""

from __future__ import annotations

from typing import Tuple

from kfchess.model.board import Board


def board_pixel_size(board: Board, cell_px: int) -> Tuple[int, int]:
    """The board's drawn size in pixels as ``(width, height)``."""
    return board.cols * cell_px, board.rows * cell_px
