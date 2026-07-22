"""Server entry point — run the Kung Fu Chess WebSocket server.

Run it from the project root (needs the server extra: ``pip install -e ".[server]"``):

    python server_main.py

Clients log in, press "Play", and are matched into games by rating; the server runs
each game and broadcasts its state to that game's players many times a second. This is
deliberately headless — it never imports the graphics/OpenCV layer — so it can run on a
plain server.
"""

import asyncio
import sys
from pathlib import Path

# Make the src/ package importable when run as ``python server_main.py``.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from kfchess.config import BOARD_CSV, SERVER_LOG  # noqa: E402
from kfchess.logging_setup import configure_logging  # noqa: E402
from kfchess.server.game_server import serve  # noqa: E402
from kfchess.tokens import load_board_csv  # noqa: E402


def main() -> None:
    configure_logging("kfchess", SERVER_LOG)  # all server activity -> server.log
    # A factory, not a single board: every game the lobby starts gets its own fresh copy.
    asyncio.run(serve(lambda: load_board_csv(BOARD_CSV)))


if __name__ == "__main__":
    main()
