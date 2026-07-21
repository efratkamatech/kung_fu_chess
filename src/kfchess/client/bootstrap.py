"""Bootstrap the thin client — assemble the windowed client over a NetClient.

The graphics analogue of the server's wiring: it builds the same :class:`BoardRenderer`
and HUD the local game uses, but fed by a :class:`SnapshotHudSource` (scores/logs from
snapshots) and driven by a :class:`ClientController` (clicks become commands) instead of
an engine. It loads the board CSV only to *size* the window; the pieces themselves come
from the server's snapshots.
"""

from __future__ import annotations

from kfchess.client.app import ThinClientApp
from kfchess.client.controller import ClientController
from kfchess.client.net_client import NetClient
from kfchess.client.snapshot_view import SnapshotHudSource
from kfchess.config import (
    BLACK_PLAYER_NAME,
    BOARD_CSV,
    BOARD_IMAGE,
    CELL_PX,
    PANEL_PX,
    PIECES_DIR,
    WHITE_PLAYER_NAME,
)
from kfchess.graphics.assets import AnimationBank
from kfchess.graphics.geometry import board_pixel_size
from kfchess.graphics.hud import Hud
from kfchess.graphics.renderer import BoardRenderer
from kfchess.graphics.sound import SoundPlayer
from kfchess.model.color import Color
from kfchess.tokens import load_board_csv


def build_thin_client_app(
    net_client: NetClient,
    white_name: str = WHITE_PLAYER_NAME,
    black_name: str = BLACK_PLAYER_NAME,
    window_name: str = "KungFu Chess (client)",
    sound_player: SoundPlayer = None,
) -> ThinClientApp:
    """Assemble the thin client: renderer + snapshot HUD + click controller."""
    board = load_board_csv(BOARD_CSV)  # for window sizing only; pieces come from snapshots
    board_w, board_h = board_pixel_size(board, CELL_PX)

    hud_source = SnapshotHudSource()
    black_hud = Hud(
        black_name, Color.BLACK, hud_source, hud_source, left_x=20,
        name_source=hud_source,
    )
    white_hud = Hud(
        white_name, Color.WHITE, hud_source, hud_source,
        left_x=PANEL_PX + board_w + 20, name_source=hud_source,
    )
    renderer = BoardRenderer(
        BOARD_IMAGE,
        AnimationBank(PIECES_DIR, CELL_PX),
        CELL_PX,
        huds=(black_hud, white_hud),
        left_panel_px=PANEL_PX,
        right_panel_px=PANEL_PX,
    )

    canvas_size = (PANEL_PX + board_w + PANEL_PX, board_h)
    player_names = {Color.WHITE: white_name, Color.BLACK: black_name}
    return ThinClientApp(
        net_client,
        renderer,
        hud_source,
        ClientController(),
        player_names,
        canvas_size,
        cell_px=CELL_PX,
        board_x_offset=PANEL_PX,
        window_name=window_name,
        sound_player=sound_player,
    )
