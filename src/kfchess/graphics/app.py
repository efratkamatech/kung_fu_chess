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
from kfchess.graphics.input import ClickFeedback, MouseInput
from kfchess.graphics.renderer import BoardRenderer

_ESC_KEY = 27
_NEW_GAME_KEYS = (ord("n"), ord("N"))


class GraphicsApp:
    """Runs the real-time frame loop against a game engine, controller, and renderer."""

    def __init__(
        self,
        engine: GameEngine,
        controller: Controller,
        renderer: BoardRenderer,
        mouse: MouseInput,
        feedback: ClickFeedback,
        player_names,
        window_name: str = "KungFu Chess",
        frame_delay_ms: int = 16,
        max_dt_ms: int = 100,
    ) -> None:
        self._engine = engine
        self._controller = controller
        self._renderer = renderer
        self._mouse = mouse
        self._feedback = feedback
        self._player_names = player_names  # {Color: name} for the game-over banner
        self._window_name = window_name
        self._frame_delay_ms = frame_delay_ms  # ~16 ms -> ~60 fps cap
        self._max_dt_ms = max_dt_ms  # clamp so a long stall doesn't teleport pieces

    @property
    def engine(self) -> GameEngine:
        """The game engine (exposed for tests and one-off scripted moves)."""
        return self._engine

    def run(self) -> bool:
        """Run the game loop. Return ``True`` if the player asked for a new game,
        ``False`` to quit (ESC or the window closed)."""
        Img.create_window(self._window_name, resizable=True)
        self._mouse.install()
        last = time.monotonic()
        while True:
            now = time.monotonic()
            dt_ms = int((now - last) * 1000)
            last = now
            self._engine.wait(min(dt_ms, self._max_dt_ms))

            selected = self._controller.selected_cell
            legal_targets = (
                self._engine.legal_targets(selected) if selected is not None else ()
            )
            frame = self._renderer.render(
                self._engine.board,
                self._engine.moving_pieces(),
                self._engine.now_ms,
                selected,
                self._engine.cooldown_progress(),
                legal_targets,
                self._feedback.current(),
            )
            if self._engine.is_game_over:
                self._renderer.draw_game_over(
                    frame, self._winner_text(), "[N] New Game    [Esc] Quit"
                )
            key = frame.show(self._window_name, self._frame_delay_ms)

            if self._engine.is_game_over and key in _NEW_GAME_KEYS:
                Img.destroy_windows()
                return True
            if key == _ESC_KEY or Img.is_window_closed(self._window_name):
                break
        Img.destroy_windows()
        return False

    def _winner_text(self) -> str:
        winner = self._engine.winner
        return f"{self._player_names[winner]} wins!" if winner is not None else "Game Over"
