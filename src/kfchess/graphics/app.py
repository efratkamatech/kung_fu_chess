"""GraphicsApp: the real-time frame loop — the windowed analogue of CommandLoop.

Where the text ``CommandLoop`` steps time explicitly with ``wait <ms>`` commands, the
windowed game advances time by the *real* wall-clock: each frame it measures how long
the previous frame took and feeds that to ``engine.wait``, so pieces move on their own
in real time. Each iteration:

    1. measure elapsed time since the last frame (dt);
    2. ``engine.wait(dt)`` — advance the clock and resolve arrivals/collisions;
    3. render the board plus the in-flight pieces, and show the frame;
    4. quit on ESC or when the window is closed.

The loop holds no game rules; it only turns real time into ``engine.wait`` calls and
asks the renderer to draw. Mouse input joins in M4.
"""

from __future__ import annotations

import time

from kfchess.control.controller import Controller
from kfchess.engine.game_engine import GameEngine
from kfchess.graphics.img import Img
from kfchess.graphics.input import MouseInput
from kfchess.graphics.renderer import BoardRenderer

_ESC_KEY = 27


class GraphicsApp:
    """Runs the real-time frame loop against a game engine, controller, and renderer."""

    def __init__(
        self,
        engine: GameEngine,
        controller: Controller,
        renderer: BoardRenderer,
        mouse: MouseInput,
        window_name: str = "KungFu Chess",
        frame_delay_ms: int = 16,
        max_dt_ms: int = 100,
    ) -> None:
        self._engine = engine
        self._controller = controller
        self._renderer = renderer
        self._mouse = mouse
        self._window_name = window_name
        self._frame_delay_ms = frame_delay_ms  # ~16 ms -> ~60 fps cap
        self._max_dt_ms = max_dt_ms  # clamp so a long stall doesn't teleport pieces

    @property
    def engine(self) -> GameEngine:
        """The game engine (exposed for tests and one-off scripted moves)."""
        return self._engine

    def run(self) -> None:
        """Loop until the user presses ESC or closes the window."""
        Img.create_window(self._window_name, resizable=True)
        self._mouse.install()
        last = time.monotonic()
        while True:
            now = time.monotonic()
            dt_ms = int((now - last) * 1000)
            last = now
            self._engine.wait(min(dt_ms, self._max_dt_ms))

            frame = self._renderer.render(
                self._engine.board,
                self._engine.moving_pieces(),
                self._engine.now_ms,
                self._controller.selected_cell,
            )
            key = frame.show(self._window_name, self._frame_delay_ms)

            if key == _ESC_KEY or Img.is_window_closed(self._window_name):
                break
        Img.destroy_windows()
