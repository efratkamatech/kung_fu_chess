"""Graphics entry point — open the game window and run the real-time loop.

Run it from the project root:

    python graphics_main.py

This is deliberately separate from ``main.py`` (the text/VPL entry point) so the
byte-exact text path stays clean and free of any OpenCV dependency.

The window shows the game in real time: pieces move on their own once a move starts.
Press ESC (or close the window) to quit. Until mouse control lands in M4, a couple of
demo moves are kicked off at startup so there is visible motion.
"""

import sys
from pathlib import Path

# Make the src/ package importable when run as ``python graphics_main.py``.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from kfchess.graphics.bootstrap import build_graphics_app  # noqa: E402
from kfchess.model.position import Position  # noqa: E402


def _seed_demo_moves(app) -> None:
    """TEMPORARY (until M4 mouse input): start a couple of moves so motion is visible."""
    engine = app.engine
    engine.request_move(Position(7, 1), Position(5, 2))  # white knight b1 -> c3
    engine.request_move(Position(6, 4), Position(4, 4))  # white pawn  e2 -> e4 (double)


def main() -> None:
    app = build_graphics_app()
    _seed_demo_moves(app)
    app.run()


if __name__ == "__main__":
    main()
