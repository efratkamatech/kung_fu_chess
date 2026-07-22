"""The shell home screen: log in with a username and password before the window opens.

Slide 4/5's "Login... do it in a shell, not via GUI." ``ask_username`` and
``ask_credentials`` prompt in the shell; ``login_loop`` drives the whole handshake
against a :class:`NetClient` — send the credentials, wait for the server's answer, and
re-prompt on a bad password (on the same connection) until accepted.

``read_line``, ``read_secret`` and ``notify`` are injected (defaulting to ``input``,
``getpass``, and ``print``) so the prompt/retry logic is unit-tested without real stdin
or a real socket.
"""

from __future__ import annotations

import getpass
from typing import Callable, Tuple

ReadLine = Callable[[str], str]


def ask_username(read_line: ReadLine = input) -> str:
    """Prompt for a username, re-asking until a non-blank one is given."""
    while True:
        name = read_line("Enter your username: ").strip()
        if name:
            return name


def ask_credentials(
    read_line: ReadLine = input, read_secret: ReadLine = getpass.getpass
) -> Tuple[str, str]:
    """Prompt for a username and a password (the password is read without echo)."""
    username = ask_username(read_line)
    password = read_secret("Enter your password: ")
    return username, password


def login_loop(
    net,
    read_line: ReadLine = input,
    read_secret: ReadLine = getpass.getpass,
    notify: Callable[[str], None] = print,
) -> str:
    """Prompt, log in, and retry on a bad password until accepted; return the username.

    ``net`` is a NetClient (already connecting): each attempt calls ``net.login`` and
    blocks on ``net.wait_for_login`` for the server's verdict.
    """
    while True:
        username, password = ask_credentials(read_line, read_secret)
        net.login(username, password)
        reason = net.wait_for_login()
        if reason is None:
            return username
        notify(f"Login failed: {reason}. Please try again.")


def lobby_loop(
    net,
    read_line: ReadLine = input,
    notify: Callable[[str], None] = print,
) -> None:
    """Offer the lobby menu — play, create a room, or join one — until seated (slides 6-7).

    Each round reads the menu choice, sends the matching request, and blocks on the
    server's answer: it returns once seated (announcing the room id if any), or reports
    why it could not start ("no opponent" / "no such room") and offers the menu again.
    """
    while True:
        choice = read_line("Play [p], create room [c], or join room [j]? ").strip().lower()
        if choice == "p":
            net.play()
        elif choice == "c":
            net.create_room()
        elif choice == "j":
            net.join_room(read_line("Room id: ").strip())
        else:
            notify("Please choose p, c, or j.")
            continue
        kind, reason = net.wait_for_match()
        if kind == "seated":
            if net.room_id is not None:
                notify(f"You're in room {net.room_id} -- share it with a friend.")
            return
        notify(f"Couldn't start a game ({reason}). Let's try again.")
