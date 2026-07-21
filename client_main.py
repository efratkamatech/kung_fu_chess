"""Thin-client entry point — connect to a Kung Fu Chess server and play in a window.

Run it from the project root (with the graphics deps and the server extra installed):

    python client_main.py --url ws://localhost:8765

It first asks for your username and password in the shell (retrying on a wrong
password), then opens the window. The first player to log in is white, the second
black; later ones watch. The window draws whatever the server sends and turns your
clicks into move commands.
"""

import argparse
import sys
from pathlib import Path

# Make the src/ package importable when run as ``python client_main.py``.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from kfchess.client.bootstrap import build_thin_client_app  # noqa: E402
from kfchess.client.home_screen import login_loop  # noqa: E402
from kfchess.client.net_client import NetClient  # noqa: E402
from kfchess.config import SERVER_HOST, SERVER_PORT  # noqa: E402
from kfchess.graphics.sound import WinsoundPlayer  # noqa: E402


def main() -> None:
    default_url = f"ws://{SERVER_HOST}:{SERVER_PORT}"
    parser = argparse.ArgumentParser(description="KungFu Chess (network client).")
    parser.add_argument("--url", default=default_url, help="server WebSocket URL")
    args = parser.parse_args()

    net_client = NetClient()
    net_client.start(args.url)     # begin connecting on a background thread
    login_loop(net_client)         # shell prompt + retry until the server accepts (slide 5)
    # A real sound player here (silent by default in the app factory) so THIS player's
    # own window beeps -- each client plays its own copy of whatever the server signals.
    build_thin_client_app(net_client, sound_player=WinsoundPlayer()).run()


if __name__ == "__main__":
    main()
