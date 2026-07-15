"""Mouse input: turn clicks in the window into Controller actions.

This is the windowed counterpart of the text layer's ``click``/``jump`` commands. It
registers a mouse callback on the window and, on each click, converts the click
position into board pixels and hands it to the existing :class:`Controller` — the same
selection-and-move logic the text path uses. Left click = select / move, right click =
jump in place.

The one graphics-specific concern is **screen pixels vs. image pixels**: the window is
resizable, so a click arrives in *window* coordinates that must be scaled back to the
board's pixel size before the Controller (which thinks in board pixels) sees it.
:func:`window_to_board` is that scaling, kept pure so it can be unit-tested.
"""

from __future__ import annotations

from typing import Tuple

from kfchess.control.controller import Controller
from kfchess.graphics.img import Img


def window_to_board(
    x: int, y: int, window_size: Tuple[int, int], board_size: Tuple[int, int]
) -> Tuple[int, int]:
    """Scale a click at window pixel ``(x, y)`` to board pixels.

    ``window_size`` is the window's current on-screen image size, ``board_size`` the
    rendered board's pixel size. If the window size is unknown yet (``0``), the click
    is passed through unscaled.
    """
    win_w, win_h = window_size
    board_w, board_h = board_size
    if win_w <= 0 or win_h <= 0:
        return int(x), int(y)
    return int(x * board_w / win_w), int(y * board_h / win_h)


class MouseInput:
    """Registers a mouse callback and routes clicks to the Controller in board pixels."""

    def __init__(
        self, controller: Controller, window_name: str, board_size: Tuple[int, int]
    ) -> None:
        self._controller = controller
        self._window_name = window_name
        self._board_size = board_size  # (width, height) of the rendered board

    def install(self) -> None:
        """Attach the callback to the window (the window must already exist)."""
        Img.set_mouse_callback(self._window_name, self._on_mouse)

    def _on_mouse(self, event: int, x: int, y: int, flags: int, param) -> None:
        """cv2 mouse callback: left click selects/moves, right click jumps."""
        if event == Img.MOUSE_LEFT_DOWN:
            board_x, board_y = self._to_board(x, y)
            self._controller.click(board_x, board_y)
        elif event == Img.MOUSE_RIGHT_DOWN:
            board_x, board_y = self._to_board(x, y)
            self._controller.jump(board_x, board_y)

    def _to_board(self, x: int, y: int) -> Tuple[int, int]:
        window_size = Img.window_image_size(self._window_name)
        return window_to_board(x, y, window_size, self._board_size)
