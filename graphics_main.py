"""Graphics entry point — open the game window.

Run it from the project root:

    python graphics_main.py

This is deliberately separate from ``main.py`` (the text/VPL entry point) so the
byte-exact text path stays clean and free of any OpenCV dependency.

M1: it loads the starting position from ``board.csv`` and shows it in a window;
press any key in the window to close. M2 turns this into the real-time frame loop.
"""

import sys
from pathlib import Path

# Make the src/ package importable when run as ``python graphics_main.py``.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from kfchess.config import BOARD_CSV, BOARD_IMAGE, CELL_PX, PIECES_DIR  # noqa: E402
from kfchess.graphics.assets import SpriteBank, load_board_csv  # noqa: E402
from kfchess.graphics.renderer import BoardRenderer  # noqa: E402


def main() -> None:
    board = load_board_csv(BOARD_CSV)
    sprite_bank = SpriteBank(PIECES_DIR, CELL_PX)
    renderer = BoardRenderer(BOARD_IMAGE, sprite_bank, CELL_PX)
    frame = renderer.render(board)
    print("Showing the starting board — press any key in the window to close.")
    frame.show("KungFu Chess")


if __name__ == "__main__":
    main()
