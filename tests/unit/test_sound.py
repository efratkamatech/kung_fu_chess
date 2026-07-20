"""Tests for the sound subsystem: game events play their matching effect."""

from kfchess.bus.event_bus import EventBus
from kfchess.bus.events import Captured, GameOver, GameStarted, MoveStarted
from kfchess.config import (
    SOUND_CAPTURE,
    SOUND_GAME_OVER,
    SOUND_GAME_START,
    SOUND_MOVE,
)
from kfchess.graphics.sound import SoundEffects, SoundPlayer
from kfchess.model.color import Color
from kfchess.model.piece import Piece
from kfchess.model.piece_type import standard_piece_types
from kfchess.model.position import Position


class SpyPlayer(SoundPlayer):
    """Records the effects it was asked to play instead of making noise."""

    def __init__(self):
        self.played = []

    def play(self, sound):
        self.played.append(sound)


def a_piece():
    return Piece(standard_piece_types().get("R"), Color.WHITE)


def test_sound_effects_play_the_matching_effect_per_event():
    bus = EventBus()
    spy = SpyPlayer()
    SoundEffects(spy).subscribe(bus)

    bus.publish(MoveStarted(a_piece(), Position(1, 0), Position(2, 0)))
    bus.publish(Captured(a_piece()))
    bus.publish(GameStarted())
    bus.publish(GameOver())

    assert spy.played == [SOUND_MOVE, SOUND_CAPTURE, SOUND_GAME_START, SOUND_GAME_OVER]


def test_default_sound_player_is_silent():
    SoundPlayer().play(SOUND_MOVE)  # the base player is a no-op: no error, no sound
