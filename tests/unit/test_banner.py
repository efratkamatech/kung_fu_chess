"""Tests for GameBanner: the start/over overlay phase, driven by bus events."""

from kfchess.bus.event_bus import EventBus
from kfchess.bus.events import Captured, GameOver, GameStarted, MoveStarted
from kfchess.graphics.banner import GameBanner
from kfchess.model.color import Color
from kfchess.model.piece import Piece
from kfchess.model.piece_type import standard_piece_types
from kfchess.model.position import Position


def a_piece():
    return Piece(standard_piece_types().get("R"), Color.WHITE)


def wired_banner():
    bus = EventBus()
    banner = GameBanner()
    banner.subscribe(bus)
    return bus, banner


def test_starts_neutral_with_no_overlay():
    banner = GameBanner()
    assert not banner.show_start
    assert not banner.is_over


def test_game_started_shows_the_start_overlay():
    bus, banner = wired_banner()
    bus.publish(GameStarted())
    assert banner.show_start
    assert not banner.is_over


def test_first_move_dismisses_the_start_overlay():
    bus, banner = wired_banner()
    bus.publish(GameStarted())
    bus.publish(MoveStarted(a_piece(), Position(1, 0), Position(2, 0)))
    assert not banner.show_start
    assert not banner.is_over


def test_a_later_move_does_not_reopen_the_start_overlay():
    bus, banner = wired_banner()
    bus.publish(GameStarted())
    bus.publish(MoveStarted(a_piece(), Position(1, 0), Position(2, 0)))  # -> playing
    bus.publish(MoveStarted(a_piece(), Position(2, 0), Position(3, 0)))  # stays playing
    assert not banner.show_start


def test_game_over_shows_the_over_overlay():
    bus, banner = wired_banner()
    bus.publish(GameStarted())
    bus.publish(GameOver())
    assert banner.is_over
    assert not banner.show_start


def test_a_capture_alone_does_not_change_the_overlay():
    bus, banner = wired_banner()
    bus.publish(GameStarted())
    bus.publish(Captured(a_piece()))  # captures are not a banner concern
    assert banner.show_start
