"""Server entry point — run the Kung Fu Chess WebSocket server.

Run it from the project root (needs the server extra: ``pip install -e ".[server]"``):

    python server_main.py

It hosts one game: the first client to connect plays white, the second black, and it
broadcasts the game state to every client many times a second. This is deliberately
headless — it never imports the graphics/OpenCV layer — so it can run on a plain server.
"""

import asyncio
import sys
from pathlib import Path

# Make the src/ package importable when run as ``python server_main.py``.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from kfchess.config import BOARD_CSV  # noqa: E402
from kfchess.server.game_server import serve  # noqa: E402
from kfchess.tokens import load_board_csv  # noqa: E402


def main() -> None:
    board = load_board_csv(BOARD_CSV)
    asyncio.run(serve(board))


if __name__ == "__main__":
    main()
