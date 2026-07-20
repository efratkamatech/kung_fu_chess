"""ThinClientApp: the networked client's frame loop — draw snapshots, send clicks.

Unlike the local :class:`GraphicsApp`, this runs no engine and never advances time: the
server owns the game. Each frame it draws the latest snapshot from :class:`NetClient`
(rebuilt into renderer inputs) and, on a click, turns the picked cells into a command
the client sends. The wall-clock window/mouse plumbing (``run`` / ``_compose_frame`` /
``_on_mouse``) is excluded from coverage like the cv2 I/O in ``img.py``; the decisions
it delegates to — handling a click, the winner text, and when to quit — are unit-tested.
"""

from __future__ import annotations

from kfchess.config import HUD_TEXT_COLOR, PANEL_BG
from kfchess.graphics.img import Img
from kfchess.graphics.input import window_to_board
from kfchess.model.position import Position
from kfchess.client.controller import ClientController
from kfchess.client.net_client import NetClient
from kfchess.client.snapshot_view import SnapshotHudSource, to_render_inputs

_ESC_KEY = 27


class ThinClientApp:
    """Draws server snapshots and forwards clicks as move commands."""

    def __init__(
        self,
        net_client: NetClient,
        renderer,
        hud_source: SnapshotHudSource,
        controller: ClientController,
        player_names,
        canvas_size,
        cell_px: int,
        board_x_offset: int,
        window_name: str = "KungFu Chess (client)",
        frame_delay_ms: int = 16,
    ) -> None:
        self._net = net_client
        self._renderer = renderer
        self._hud_source = hud_source
        self._controller = controller
        self._player_names = player_names
        self._canvas_size = canvas_size  # (width, height) of the rendered canvas
        self._cell_px = cell_px
        self._board_x_offset = board_x_offset  # left panel width to subtract off clicks
        self._window_name = window_name
        self._frame_delay_ms = frame_delay_ms

    def _handle_click(self, canvas_x: int, canvas_y: int) -> None:
        """Turn a click (in canvas pixels) into a move command and queue it to send."""
        snapshot = self._net.latest()
        if snapshot is None:
            return  # nothing drawn yet; ignore the click
        cell = Position(
            canvas_y // self._cell_px,
            (canvas_x - self._board_x_offset) // self._cell_px,
        )
        command = self._controller.click(cell, snapshot, self._net.color)
        if command is not None:
            self._net.queue_command(command)

    def _winner_text(self, snapshot) -> str:
        winner = snapshot.winner
        return (
            f"{self._player_names[winner]} wins!" if winner is not None else "Game Over"
        )

    def _should_quit(self, key: int, window_closed: bool) -> bool:
        """The client quits on ESC or when the window is closed."""
        return key == _ESC_KEY or window_closed

    def run(self) -> None:  # pragma: no cover  (real-time window/mouse loop)
        Img.create_window(self._window_name, resizable=True)
        Img.set_mouse_callback(self._window_name, self._on_mouse)
        while True:
            snapshot = self._net.latest()
            frame = (
                self._compose_frame(snapshot)
                if snapshot is not None
                else self._waiting_frame()
            )
            key = frame.show(self._window_name, self._frame_delay_ms)
            if self._should_quit(key, Img.is_window_closed(self._window_name)):
                Img.destroy_windows()
                return

    def _compose_frame(self, snapshot):  # pragma: no cover  (assembles the render call)
        self._hud_source.update(snapshot)
        board, moving, cooldowns = to_render_inputs(snapshot)
        frame = self._renderer.render(
            board, moving, snapshot.now_ms, self._controller.selected, cooldowns
        )
        if snapshot.phase == "over":
            self._renderer.draw_game_over(
                frame, self._winner_text(snapshot), "[Esc] Quit"
            )
        elif snapshot.phase == "start":
            self._renderer.draw_start_banner(
                frame, "KungFu Chess", "Click your piece to move"
            )
        return frame

    def _waiting_frame(self):  # pragma: no cover  (shown only before the first snapshot)
        width, height = self._canvas_size
        frame = Img.blank(width, height, 3, PANEL_BG)
        frame.put_text_centered("Connecting...", width // 2, height // 2, 1.0, HUD_TEXT_COLOR, 2)
        return frame

    def _on_mouse(self, event, x, y, flags, param):  # pragma: no cover  (cv2 callback)
        if event == Img.MOUSE_LEFT_DOWN:
            canvas_x, canvas_y = window_to_board(
                x, y, Img.window_image_size(self._window_name), self._canvas_size
            )
            self._handle_click(canvas_x, canvas_y)
