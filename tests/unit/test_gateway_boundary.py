"""The gateway must not know the game. Enforced, not just intended.

Risk #4 in the implementation plan: "the gateway acquires game state". It would not
arrive as a decision — nobody sets out to put chess in the socket layer. It arrives as
one convenient import, and then a small thing that seemed harmless to do on this side
because the object was already there. So the import is what this forbids.

The rule is read off the source rather than by importing the modules, so it holds for
code on paths a test never runs, and cannot be satisfied by an import that happens to be
lazy.
"""

import ast
from pathlib import Path

import pytest

GATEWAY = Path(__file__).resolve().parents[2] / "src" / "kfchess" / "gateway"

# What a pipe has no business knowing: the rules, the board, and the process that owns
# them. `shared` is allowed — the wire vocabulary is not the game — and so is `bus`,
# which is how it speaks at all.
FORBIDDEN = ("kfchess.engine", "kfchess.model", "kfchess.rules", "kfchess.movement",
             "kfchess.server", "kfchess.observers", "kfchess.graphics", "kfchess.client",
             # And, from S3, the shared state. A gateway that could read the directory
             # could check a seat token, and then every replica of the thing built to be
             # thrown away and replaced would be a place where security is decided. The
             # shard checks tokens; this forwards a string it cannot read.
             "kfchess.services", "redis")


def imported_modules(path: Path):
    """Every module named by an import anywhere in ``path``, lazy ones included."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module


@pytest.mark.parametrize("path", sorted(GATEWAY.glob("*.py")), ids=lambda p: p.name)
def test_the_gateway_does_not_import_the_game(path):
    offenders = [
        module
        for module in imported_modules(path)
        if module.startswith(FORBIDDEN)
    ]
    assert offenders == [], (
        f"{path.name} imports {offenders}. The gateway moves text between a socket and "
        f"a subject; anything it can reach into, it will eventually decide with."
    )


def test_the_rule_is_looking_at_the_right_place():
    """A guard on the guard: if the package moved, the loop above would pass vacuously."""
    assert {path.name for path in GATEWAY.glob("*.py")} >= {"app.py", "router.py"}
