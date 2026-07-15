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
from kfchess.graphics.hud import Hud
from kfchess.graphics.input import MouseInput
from kfchess.graphics.renderer import BoardRenderer


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

    board_px = board.cols * CELL_PX
    hud = Hud(moves_log, score_board, WHITE_PLAYER_NAME, BLACK_PLAYER_NAME, board_px)
    renderer = BoardRenderer(
        BOARD_IMAGE, AnimationBank(PIECES_DIR, CELL_PX), CELL_PX, hud=hud, panel_px=PANEL_PX
    )

    # The mouse maps to the full canvas (board + panel); clicks in the panel fall off
    # the board and the Controller ignores them.
    canvas_size = (board_px + PANEL_PX, board.rows * CELL_PX)
    mouse = MouseInput(controller, window_name, canvas_size, CELL_PX)
    return GraphicsApp(engine, controller, renderer, mouse, window_name)
