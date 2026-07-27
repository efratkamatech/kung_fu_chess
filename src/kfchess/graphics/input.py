"""Mouse input: turn clicks in the window into Controller actions.

This is the windowed counterpart of the text layer's ``click``/``jump`` commands. It
registers a mouse callback on the window and, on each click, converts the click
position into board pixels and hands it to the existing :class:`Controller` — the same
selection-and-move logic the text path uses. Left click = select / move, right click =
jump in place.

Clicks arrive already in *image* pixels: OpenCV scales them itself when a
``WINDOW_NORMAL`` window is shown at a size other than the image's, so the callback
sees board pixels no matter how the user has dragged the window. Scaling them a second
time here is what broke clicks on a shrunk window, so we pass them straight through.
"""

from __future__ import annotations

import time
from typing import Optional, Tuple

from kfchess.config import INVALID_FLASH_SECONDS
from kfchess.control.controller import ClickOutcome, Controller
from kfchess.graphics.img import Img
from kfchess.model.position import Position


class ClickFeedback:
    """Remembers a cell to flash red for a short moment after an illegal-move click.

    Written by the mouse handler, read by the frame loop; timed on the wall clock so
    the two stay in sync without threading through the game clock.
    """

    def __init__(self, duration_s: float = INVALID_FLASH_SECONDS) -> None:
        self._duration_s = duration_s
        self._cell: Optional[Position] = None
        self._expires_at = 0.0

    def flash(self, cell: Position) -> None:
        """Start flashing ``cell`` from now for the configured duration."""
        self._cell = cell
        self._expires_at = time.monotonic() + self._duration_s

    def current(self) -> Optional[Position]:
        """The cell to flash right now, or ``None`` once the flash has elapsed."""
        if self._cell is not None and time.monotonic() < self._expires_at:
            return self._cell
        return None


class MouseInput:
    """Registers a mouse callback and routes clicks to the Controller in board pixels."""

    def __init__(
        self,
        controller: Controller,
        window_name: str,
        board_x_offset: int = 0,
        feedback: Optional[ClickFeedback] = None,
    ) -> None:
        self._controller = controller
        self._window_name = window_name
        self._board_x_offset = board_x_offset  # left panel width to subtract off clicks
        self._feedback = feedback or ClickFeedback()

    def install(self) -> None:  # pragma: no cover  (registers the cv2 window callback)
        """Attach the callback to the window (the window must already exist)."""
        Img.set_mouse_callback(self._window_name, self._on_mouse)

    def _on_mouse(self, event: int, x: int, y: int, flags: int, param) -> None:
        """cv2 mouse callback: left click selects/moves (or jumps a re-clicked piece),
        right click jumps."""
        if event == Img.MOUSE_LEFT_DOWN:
            board_x, board_y = self._to_board(x, y)
            if self._controller.cell_at(board_x, board_y) == self._controller.selected_cell:
                # Clicking the already-selected piece again means "jump in place".
                self._controller.jump(board_x, board_y)
                self._controller.deselect()
            elif self._controller.click(board_x, board_y) is ClickOutcome.ILLEGAL:
                # Tried to move to a cell the piece can't reach: flash it red.
                self._feedback.flash(self._controller.cell_at(board_x, board_y))
        elif event == Img.MOUSE_RIGHT_DOWN:
            board_x, board_y = self._to_board(x, y)
            self._controller.jump(board_x, board_y)

    def _to_board(self, x: int, y: int) -> Tuple[int, int]:
        # Shift into board-local pixels; a click in a side panel lands off the board
        # (negative or past the last column), which the Controller ignores.
        return int(x) - self._board_x_offset, int(y)
