from kfchess.config import SOUND_GAME_START
from kfchess.graphics.app import GraphicsApp
from kfchess.graphics.bootstrap import build_graphics_app
from kfchess.graphics.sound import SoundPlayer
from kfchess.model.color import Color
from kfchess.model.position import Position


class SpyPlayer(SoundPlayer):
    def __init__(self):
        self.played = []

    def play(self, sound):
        self.played.append(sound)


def test_build_graphics_app_returns_a_wired_app():
    app = build_graphics_app()
    assert isinstance(app, GraphicsApp)
    # the engine is real and playable through the wiring
    assert app.engine.request_move(Position(7, 1), Position(5, 2)) is True


def test_build_announces_game_started_on_the_bus():
    spy = SpyPlayer()
    build_graphics_app(sound_player=spy)
    assert spy.played == [SOUND_GAME_START]  # GameStarted was published once, at build


def test_build_graphics_app_carries_the_player_names():
    app = build_graphics_app(white_name="Efrat", black_name="Dan")
    assert app._player_names == {Color.WHITE: "Efrat", Color.BLACK: "Dan"}
