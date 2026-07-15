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
from kfchess.graphics.assets import SpriteBank, load_board_csv
from kfchess.graphics.renderer import BoardRenderer


def build_graphics_app(window_name: str = "KungFu Chess") -> GraphicsApp:
    """Load assets, build the core game, and return the ready-to-run windowed app."""
    board = load_board_csv(BOARD_CSV)
    engine, _controller = build_game(board)  # _controller wired to the mouse in M4
    sprite_bank = SpriteBank(PIECES_DIR, CELL_PX)
    renderer = BoardRenderer(BOARD_IMAGE, sprite_bank, CELL_PX)
    return GraphicsApp(engine, renderer, window_name)
