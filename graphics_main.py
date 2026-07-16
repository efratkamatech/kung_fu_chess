"""Graphics entry point — open the game window and run the real-time loop.

Run it from the project root:

    python graphics_main.py

This is deliberately separate from ``main.py`` (the text/VPL entry point) so the
byte-exact text path stays clean and free of any OpenCV dependency.

Controls:
    - Left click a piece to select it (a green outline marks the selection); left
      click a destination to move it there.
    - Left click the selected piece again, or right click a piece, to jump in place.
    - The game runs in real time — pieces move on their own once a move starts, with
      no turns.
    - When a king is captured, a Game Over banner offers [N] New Game or [Esc] Quit.
"""

import argparse
import sys
from pathlib import Path

# Make the src/ package importable when run as ``python graphics_main.py``.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from kfchess.config import BLACK_PLAYER_NAME, WHITE_PLAYER_NAME  # noqa: E402
from kfchess.graphics.bootstrap import build_graphics_app  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="KungFu Chess (graphics).")
    parser.add_argument("--white", default=WHITE_PLAYER_NAME, help="white player's name")
    parser.add_argument("--black", default=BLACK_PLAYER_NAME, help="black player's name")
    args = parser.parse_args()

    # run() returns True when the player picks "New Game" on the game-over banner, so
    # we build a fresh game and loop; it returns False to quit.
    while build_graphics_app(white_name=args.white, black_name=args.black).run():
        pass


if __name__ == "__main__":
    main()
