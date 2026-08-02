"""The offline game must stay playable on a laptop with nothing installed. Enforced.

The companion to ``test_gateway_boundary``, pointing the other way. That one keeps the
game out of the pipe; this one keeps the infrastructure out of the game.

Kung Fu Chess is playable three ways, and two of them involve no server at all: the text
core reading a fixture from stdin, and the windowed game running both colours on one
machine. Those came first and they still have to work — `python graphics_main.py` and
nothing else, no NATS, no Redis, no database, no Docker.

Nothing threatens that on purpose. It would go the way these things always go: something
in the engine wants a room id, or the renderer wants to know whether the opponent has
dropped, and one import later the offline game will not start without a message bus that
is not there. So the import is what this forbids, and it is read off the source rather
than by importing the modules, so it holds for code on paths a test never runs and cannot
be satisfied by an import that happens to be lazy.

The rule is not "no networking anywhere" — the *client* is allowed all of it, because a
client without a network is nothing. It is that the layers the offline game is built from
own nothing but the game.
"""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "kfchess"

# What the offline game is made of: the rules and the board, the two front ends that
# drive them, and the loop in between.
LOCAL_PACKAGES = (
    "model",
    "movement",
    "rules",
    "engine",
    "text_io",
    "graphics",
    "app",
    "control",
)

# What none of it may reach for. `bus.event_bus` is fine and deliberately not in here:
# events between objects in one process are how the windowed game already scores itself.
# `bus.message_bus` is the opposite thing wearing a similar name — text to another
# process — and it is the one that drags a server in behind it.
FORBIDDEN = (
    "kfchess.server",
    "kfchess.services",
    "kfchess.gateway",
    "kfchess.client",
    # The core may not import the observability package either. That rule was written
    # into `obs/measures.py` when the metrics were added and enforced by nothing but
    # care, which is precisely the arrangement the dependency law exists to replace:
    # timing a game from inside the engine is one convenient import away, and the engine
    # has never imported anything above itself.
    "kfchess.obs",
    "kfchess.bus.message_bus",
    "kfchess.bus.envelope",
    "kfchess.bus.subjects",
    "nats",
    "redis",
    "websockets",
    "psycopg",
)


def forbids(module: str) -> bool:
    """Whether ``module`` is one of the forbidden packages, or lives inside one.

    A plain ``startswith`` is not this test: ``kfchess.obs`` would then also forbid
    ``kfchess.observers``, which is the game's own score and move log and belongs
    exactly where it is. A package boundary ends at a dot or at the end of the name.
    """
    return any(
        module == package or module.startswith(package + ".") for package in FORBIDDEN
    )


def imported_modules(path: Path):
    """Every module named by an import anywhere in ``path``, lazy ones included."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module


def local_sources():
    """Every source file the offline game is built from."""
    return sorted(
        path
        for package in LOCAL_PACKAGES
        for path in (SRC / package).glob("*.py")
    )


@pytest.mark.parametrize("path", local_sources(), ids=lambda p: f"{p.parent.name}/{p.name}")
def test_the_local_game_does_not_import_the_infrastructure(path):
    offenders = [
        module for module in imported_modules(path) if forbids(module)
    ]
    assert offenders == [], (
        f"{path.parent.name}/{path.name} imports {offenders}. The offline game has to "
        f"start with nothing installed and nothing running; one import of a service is "
        f"all it takes for it to stop."
    )


def test_the_rule_is_looking_at_the_right_place():
    """A guard on the guard: if a package moved, the loop above would pass vacuously."""
    checked = {f"{path.parent.name}/{path.name}" for path in local_sources()}
    assert {
        "model/board.py",
        "engine/game_engine.py",
        "graphics/app.py",
        "app/bootstrap.py",
        "text_io/board_parser.py",
    } <= checked
