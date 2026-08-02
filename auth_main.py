"""Auth entry point — check passwords, and nothing else.

    python auth_main.py

Needs the server extra, NATS to listen on, and the accounts database (PostgreSQL when
``DATABASE_URL`` names one, SQLite otherwise). It runs no games, holds no sockets, and
remembers nothing between requests — so the way to admit more players per second is to
start another one of these, which is the entire reason it exists as its own process.

Measured before the split: one login costs 36.5 ms of PBKDF2, and while it ran on the
shard's thread the games it was running stopped. About twelve admissions a second, and no
better for having fewer games.
"""

import asyncio
import sys
from pathlib import Path

# Make the src/ package importable when run as ``python auth_main.py``.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from kfchess.auth.service import serve  # noqa: E402
from kfchess.config import SERVER_LOG  # noqa: E402
from kfchess.logging_setup import configure_logging  # noqa: E402


def main() -> None:
    configure_logging("kfchess", SERVER_LOG.with_name("auth.log"))
    asyncio.run(serve())


if __name__ == "__main__":
    main()
