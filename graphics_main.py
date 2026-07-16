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

import sys
from pathlib import Path

# Make the src/ package importable when run as ``python graphics_main.py``.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from kfchess.graphics.bootstrap import build_graphics_app  # noqa: E402


def main() -> None:
    # run() returns True when the player picks "New Game" on the game-over banner, so
    # we build a fresh game and loop; it returns False to quit.
    while build_graphics_app().run():
        pass


if __name__ == "__main__":
    main()
