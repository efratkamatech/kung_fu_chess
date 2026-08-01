"""Server entry point — run the games, either way.

Run it from the project root (needs the server extra: ``pip install -e ".[server]"``).

Two players on one machine, with nothing else running::

    python server_main.py --solo

The gateway and the shard are both in this process, the bus between them is a function
call, and the shared state is a dictionary. No NATS, no Redis, no database server, no
Docker. Point the clients at ``ws://localhost:8765`` exactly as they would be pointed at
a real gateway — nothing about them changes.

As one shard of a real deployment::

    python server_main.py

Runs the games and nothing else: no listener, no sockets, and no ``websockets`` import
anywhere beneath it. Players reach it through a gateway (``gateway_main.py``) over NATS,
which is what lets the two scale apart — connections are cheap and numerous, games are
expensive and stateful. It needs NATS and Redis, plus a PostgreSQL if ``DATABASE_URL``
names one; ``docker compose up`` provides all three.

The game is the same game either way. The difference is two objects, chosen in
``kfchess.server.solo`` and in ``shard.serve``, and nothing above them can tell.
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Make the src/ package importable when run as ``python server_main.py``.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from kfchess.config import BOARD_CSV, SERVER_LOG  # noqa: E402
from kfchess.logging_setup import configure_logging  # noqa: E402
from kfchess.server.shard import serve  # noqa: E402
from kfchess.server.solo import serve as serve_solo  # noqa: E402
from kfchess.shared.tokens import load_board_csv  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="KungFu Chess (server).")
    parser.add_argument(
        "--solo",
        action="store_true",
        help="run the gateway and the shard in this process, with no infrastructure",
    )
    args = parser.parse_args()

    configure_logging("kfchess", SERVER_LOG)  # all server activity -> server.log
    # A factory, not a single board: every game started gets its own fresh copy.
    new_board = lambda: load_board_csv(BOARD_CSV)  # noqa: E731
    asyncio.run(serve_solo(new_board) if args.solo else serve(new_board))


if __name__ == "__main__":
    main()
