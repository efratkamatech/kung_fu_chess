"""Gateway entry point — run one WS gateway.

    python gateway_main.py

Holds the WebSocket connections and bridges them onto NATS. It runs no game and knows no
rules: every message a client sends is forwarded to the shard, and every answer comes
back the same way. Needs the ``server`` extra, and a NATS server to talk to (``NATS_URL``,
which ``docker compose`` sets for you).

Run more than one by giving each a different ``KFC_GATEWAY_ID`` and port: they need no
knowledge of each other, because every connection's replies are addressed to a subject
only its own gateway is subscribed to.
"""

import asyncio
import sys
from pathlib import Path

# Make the src/ package importable when run as ``python gateway_main.py``.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from kfchess.config import CLIENT_LOG, GATEWAY_ID  # noqa: E402
from kfchess.gateway.app import serve  # noqa: E402
from kfchess.logging_setup import configure_logging  # noqa: E402


def main() -> None:
    configure_logging("kfchess", CLIENT_LOG.with_name("gateway.log"))
    asyncio.run(serve(GATEWAY_ID))


if __name__ == "__main__":
    main()
