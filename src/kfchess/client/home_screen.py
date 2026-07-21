"""The shell home screen: ask the player for a username before the window opens.

Slide 4's "Login with username... do it in a shell, not via GUI" -- kept as simple as
the slide asks: no password yet (that's M4), just a name to show in the HUD instead of
a hardcoded default. ``read_line`` is injected (defaults to the real ``input``) so the
prompt loop is unit-tested without blocking on real stdin.
"""

from __future__ import annotations

from typing import Callable

ReadLine = Callable[[str], str]


def ask_username(read_line: ReadLine = input) -> str:
    """Prompt for a username, re-asking until a non-blank one is given."""
    while True:
        name = read_line("Enter your username: ").strip()
        if name:
            return name
