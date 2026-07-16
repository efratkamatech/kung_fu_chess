"""Bootstrap the windowed game — the graphics layer's wiring hub.

The graphics analogue of ``app/bootstrap.py``: it assembles everything the windowed
game needs and hands back a ready :class:`GraphicsApp`. Crucially it **reuses the
core's own wiring** — ``build_game`` builds the very same Clock / RuleEngine / arbiter
/ engine / controller that the text path uses — so the graphics game and the text game
run on identical logic; only the input (mouse), output (window), and observers differ.
"""

from __future__ import annotations

from kfchess.app.bootstrap import build_game
from kfchess.config import (
    BLACK_PLAYER_NAME,
    BOARD_CSV,
    BOARD_IMAGE,
    CELL_PX,
    PANEL_PX,
    PIECES_DIR,
    WHITE_PLAYER_NAME,
)
from kfchess.graphics.app import GraphicsApp
from kfchess.graphics.assets import AnimationBank, load_board_csv
from kfchess.graphics.events import MovesLog, ScoreBoard
from kfchess.graphics.geometry import board_pixel_size
from kfchess.graphics.hud import Hud
from kfchess.graphics.input import MouseInput
from kfchess.graphics.renderer import BoardRenderer
from kfchess.model.color import Color


def build_graphics_app(window_name: str = "KungFu Chess") -> GraphicsApp:
    """Load assets, build the core game, wire input + observers, and return the app."""
    board = load_board_csv(BOARD_CSV)
    engine, controller = build_game(board)

    # Observers: register onto the engine's shared list so they receive both the
    # engine's move-starts and the arbiter's captures.
    moves_log = MovesLog(board.rows)
    score_board = ScoreBoard()
    engine.add_observer(moves_log)
    engine.add_observer(score_board)

    # Two side panels: black on the left, white on the right, board in the middle.
    board_w, board_h = board_pixel_size(board, CELL_PX)
    black_hud = Hud(BLACK_PLAYER_NAME, Color.BLACK, moves_log, score_board, left_x=20)
    white_hud = Hud(
        WHITE_PLAYER_NAME, Color.WHITE, moves_log, score_board,
        left_x=PANEL_PX + board_w + 20,
    )
    renderer = BoardRenderer(
        BOARD_IMAGE,
        AnimationBank(PIECES_DIR, CELL_PX),
        CELL_PX,
        huds=(black_hud, white_hud),
        left_panel_px=PANEL_PX,
        right_panel_px=PANEL_PX,
    )

    # The mouse maps to the full canvas (left panel + board + right panel); the board
    # sits PANEL_PX from the left, so clicks are shifted by that offset and panel
    # clicks fall off the board (the Controller ignores them).
    canvas_size = (PANEL_PX + board_w + PANEL_PX, board_h)
    mouse = MouseInput(controller, window_name, canvas_size, board_x_offset=PANEL_PX)
    return GraphicsApp(engine, controller, renderer, mouse, window_name)
