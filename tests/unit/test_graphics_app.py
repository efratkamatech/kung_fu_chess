from types import SimpleNamespace

from kfchess.graphics.app import _CONTINUE, _QUIT, _RESTART, GraphicsApp
from kfchess.model.color import Color

_NAMES = {Color.WHITE: "Efrat", Color.BLACK: "Dan"}
_N, _ESC, _OTHER = ord("n"), 27, ord("x")


def an_app(winner=None):
    # Only the engine (for winner) and player names matter for these unit tests.
    return GraphicsApp(SimpleNamespace(winner=winner), None, None, None, None, _NAMES)


def test_new_game_key_restarts_only_when_the_game_is_over():
    app = an_app()
    assert app._next_action(_N, True, False) == _RESTART
    assert app._next_action(ord("N"), True, False) == _RESTART
    assert app._next_action(_N, False, False) == _CONTINUE  # N mid-game just continues


def test_esc_or_closed_window_quits():
    app = an_app()
    assert app._next_action(_ESC, False, False) == _QUIT
    assert app._next_action(-1, False, True) == _QUIT


def test_any_other_key_continues():
    assert an_app()._next_action(_OTHER, False, False) == _CONTINUE


def test_winner_text_uses_the_player_name_or_falls_back():
    assert an_app(winner=Color.WHITE)._winner_text() == "Efrat wins!"
    assert an_app(winner=Color.BLACK)._winner_text() == "Dan wins!"
    assert an_app(winner=None)._winner_text() == "Game Over"
