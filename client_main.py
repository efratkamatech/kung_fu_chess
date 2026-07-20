"""Thin-client entry point — connect to a Kung Fu Chess server and play in a window.

Run it from the project root (with the graphics deps and the server extra installed):

    python client_main.py --url ws://localhost:8765

The first client to connect plays white, the second black; later clients watch. The
window draws whatever the server sends and turns your clicks into move commands.
"""

import argparse
import sys
from pathlib import Path

# Make the src/ package importable when run as ``python client_main.py``.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from kfchess.client.bootstrap import build_thin_client_app  # noqa: E402
from kfchess.client.net_client import NetClient  # noqa: E402
from kfchess.config import (  # noqa: E402
    BLACK_PLAYER_NAME,
    SERVER_HOST,
    SERVER_PORT,
    WHITE_PLAYER_NAME,
)


def main() -> None:
    default_url = f"ws://{SERVER_HOST}:{SERVER_PORT}"
    parser = argparse.ArgumentParser(description="KungFu Chess (network client).")
    parser.add_argument("--url", default=default_url, help="server WebSocket URL")
    parser.add_argument("--white", default=WHITE_PLAYER_NAME, help="white player's name")
    parser.add_argument("--black", default=BLACK_PLAYER_NAME, help="black player's name")
    args = parser.parse_args()

    net_client = NetClient()
    net_client.start(args.url)
    build_thin_client_app(net_client, white_name=args.white, black_name=args.black).run()


if __name__ == "__main__":
    main()
