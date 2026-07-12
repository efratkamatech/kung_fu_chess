"""TextTestRunner: drive the program through its public command path.

It feeds fixture text through the same wiring the real program uses and returns the
exact stdout the program would produce (including the trailing newline that main's
print adds). Comparing that to a fixture's expected .out file is the same
byte-for-byte check VPL performs.
"""

from __future__ import annotations

from pathlib import Path

from kfchess.app.bootstrap import build_command_loop


def program_output(input_text: str) -> str:
    """Return the exact stdout the program would emit for ``input_text``."""
    output = build_command_loop().run(input_text)
    # Mirror main(): a non-empty result is printed (adding a newline); empty prints
    # nothing at all.
    return output + "\n" if output else ""


def run_fixture_file(in_path: Path) -> str:
    """Run a ``.in`` fixture file and return the program's stdout."""
    return program_output(in_path.read_text())
