"""Top-level entry point — run this file directly (e.g. in VPL).

The program is organized as a package under ``src/kfchess``. This thin launcher
adds that ``src`` folder to Python's import path and starts the program, so it can
be run with a plain ``python main.py`` from the project root — no PYTHONPATH or
installation needed. This is the file VPL should execute.
"""

import sys
from pathlib import Path

# Make the src/ package importable no matter where the program is launched from.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from kfchess.main import main  # noqa: E402  (import must follow the path setup)

if __name__ == "__main__":
    # Byte-exact '\n' output on every platform (matches the Linux grader).
    sys.stdout.reconfigure(newline="\n")
    main()
