"""Bootstrap the windowed game — the graphics layer's wiring hub.

The graphics analogue of ``app/bootstrap.py``: it assembles everything the windowed
game needs and hands back a ready :class:`GraphicsApp`. Crucially it **reuses the
core's own wiring** — ``build_game`` builds the very same Clock / RuleEngine / arbiter
/ engine / controller that the text path uses — so the graphics game and the text game
run on identical logic; only the input (mouse) and output (window) differ.
"""

from __future__ import annotations

from kfchess.app.bootstrap import build_game
from kfchess.config import BOARD_CSV, BOARD_IMAGE, CELL_PX, PIECES_DIR
from kfchess.graphics.app import GraphicsApp
from kfchess.graphics.assets import AnimationBank, load_board_csv
from kfchess.graphics.input import MouseInput
from kfchess.graphics.renderer import BoardRenderer


def build_graphics_app(window_name: str = "KungFu Chess") -> GraphicsApp:
    """Load assets, build the core game, wire mouse input, and return the windowed app."""
    board = load_board_csv(BOARD_CSV)
    engine, controller = build_game(board)
    animation_bank = AnimationBank(PIECES_DIR, CELL_PX)
    renderer = BoardRenderer(BOARD_IMAGE, animation_bank, CELL_PX)
    board_size = (board.cols * CELL_PX, board.rows * CELL_PX)
    mouse = MouseInput(controller, window_name, board_size)
    return GraphicsApp(engine, controller, renderer, mouse, window_name)
