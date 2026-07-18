from kfchess.graphics.app import GraphicsApp
from kfchess.graphics.bootstrap import build_graphics_app
from kfchess.model.color import Color
from kfchess.model.position import Position


def test_build_graphics_app_returns_a_wired_app():
    app = build_graphics_app()
    assert isinstance(app, GraphicsApp)
    # the engine is real and playable through the wiring
    assert app.engine.request_move(Position(7, 1), Position(5, 2)) is True


def test_build_graphics_app_carries_the_player_names():
    app = build_graphics_app(white_name="Efrat", black_name="Dan")
    assert app._player_names == {Color.WHITE: "Efrat", Color.BLACK: "Dan"}
