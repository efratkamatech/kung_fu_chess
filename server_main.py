"""Shard entry point — run one game server.

Run it from the project root (needs the server extra: ``pip install -e ".[server]"``):

    python server_main.py

Runs the games and nothing else: no listener, no sockets, and no ``websockets`` import
anywhere beneath it. Players reach it through a gateway (``gateway_main.py``) over NATS,
which is what lets the two scale apart — connections are cheap and numerous, games are
expensive and stateful. It needs a NATS server, and a PostgreSQL if ``DATABASE_URL`` names
one; ``docker compose up`` provides both.
"""

import asyncio
import sys
from pathlib import Path

# Make the src/ package importable when run as ``python server_main.py``.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from kfchess.config import BOARD_CSV, SERVER_LOG  # noqa: E402
from kfchess.logging_setup import configure_logging  # noqa: E402
from kfchess.server.shard import serve  # noqa: E402
from kfchess.shared.tokens import load_board_csv  # noqa: E402


def main() -> None:
    configure_logging("kfchess", SERVER_LOG)  # all shard activity -> server.log
    # A factory, not a single board: every game the shard starts gets its own fresh copy.
    asyncio.run(serve(lambda: load_board_csv(BOARD_CSV)))


if __name__ == "__main__":
    main()
