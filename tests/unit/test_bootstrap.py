from kfchess.app.bootstrap import build_command_loop
from kfchess.app.command_loop import CommandLoop


def test_build_returns_a_command_loop():
    assert isinstance(build_command_loop(), CommandLoop)


def test_built_loop_is_fully_wired_and_runs():
    out = build_command_loop().run("Board:\nwK\nCommands:\nprint board\n")
    assert out == "wK"


def test_built_loop_handles_click_and_move():
    # Exercises the per-fixture game factory wired in bootstrap.
    text = (
        "Board:\nwK . .\n. . .\n. . .\n"
        "Commands:\nclick 50 50\nclick 150 150\nprint board\n"
    )
    assert build_command_loop().run(text) == ". . .\n. wK .\n. . ."
