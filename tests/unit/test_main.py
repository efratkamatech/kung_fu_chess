import io

from kfchess import main as main_module


# main() is the I/O boundary: the only place we replace the process's stdin/stdout.
# This is not a substitute for dependency injection (the logic lives in testable
# layers) -- it just exercises the thin read-stdin / print-stdout shell.
def test_main_prints_program_output(capsys, monkeypatch):
    monkeypatch.setattr(
        "sys.stdin", io.StringIO("Board:\nwK bK\nCommands:\nprint board\n")
    )
    main_module.main()
    assert capsys.readouterr().out == "wK bK\n"


def test_main_prints_nothing_when_output_is_empty(capsys, monkeypatch):
    # A fixture with an empty Commands section yields no output at all.
    monkeypatch.setattr("sys.stdin", io.StringIO("Board:\nwK\nCommands:\n"))
    main_module.main()
    assert capsys.readouterr().out == ""
