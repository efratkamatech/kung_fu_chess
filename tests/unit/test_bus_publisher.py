"""Tests for BusPublisher: engine observer callbacks become published bus events."""

from kfchess.bus import topics
from kfchess.bus.event_bus import EventBus
from kfchess.bus.publisher import BusPublisher
from kfchess.model.color import Color
from kfchess.model.piece import Piece
from kfchess.model.piece_type import standard_piece_types
from kfchess.model.position import Position


def a_piece():
    return Piece(standard_piece_types().get("R"), Color.WHITE)


def collect(bus, topic):
    """Subscribe a list-collector to ``topic`` and return the list it fills."""
    received = []
    bus.subscribe(topic, received.append)
    return received


def test_move_started_callback_publishes_a_move_event():
    bus = EventBus()
    moves = collect(bus, topics.MOVE_STARTED)
    piece = a_piece()

    BusPublisher(bus).on_move_started(piece, Position(1, 0), Position(3, 0))

    assert len(moves) == 1
    assert (moves[0].piece, moves[0].source, moves[0].target) == (
        piece,
        Position(1, 0),
        Position(3, 0),
    )


def test_capture_callback_publishes_a_captured_event():
    bus = EventBus()
    captures = collect(bus, topics.CAPTURE)
    victim = a_piece()

    BusPublisher(bus).on_capture(victim)

    assert len(captures) == 1
    assert captures[0].victim is victim


def test_game_over_callback_publishes_a_game_over_event():
    bus = EventBus()
    overs = collect(bus, topics.GAME_OVER)

    BusPublisher(bus).on_game_over()

    assert len(overs) == 1
    assert overs[0].winner is None
