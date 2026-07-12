"""Kung Fu Chess — program entry point.

Repository: https://github.com/efratkamatech/kung_fu_chess.git

The launch point, kept intentionally tiny. It builds the application via the
bootstrap and runs it against standard input, writing the result to standard
output (byte-exact: no prompts, no debug text).

All wiring lives in ``app.bootstrap``; all command logic lives in
``app.command_loop``. ``main`` only starts things — it never grows as the app does.
"""

from __future__ import annotations

import sys

from kfchess.app.bootstrap import build_command_loop


def main() -> None:
    output = build_command_loop().run(sys.stdin.read())
    if output:
        print(output)


if __name__ == "__main__":
    main()
