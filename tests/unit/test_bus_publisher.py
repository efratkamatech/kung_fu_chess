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

    BusPublisher(bus).on_move_started(piece, Position(1, 0), Position(3, 0), 500, 2500)

    assert len(moves) == 1
    assert (
        moves[0].piece,
        moves[0].source,
        moves[0].target,
        moves[0].start_ms,
        moves[0].arrival_ms,
    ) == (piece, Position(1, 0), Position(3, 0), 500, 2500)


def test_settled_callback_publishes_a_settled_event():
    bus = EventBus()
    settles = collect(bus, topics.SETTLED)
    piece = a_piece()

    BusPublisher(bus).on_settled(piece, Position(3, 0), 2500, 1000)

    assert len(settles) == 1
    assert (settles[0].piece, settles[0].cell, settles[0].at_ms, settles[0].cooldown_ms) == (
        piece,
        Position(3, 0),
        2500,
        1000,
    )


def test_capture_callback_publishes_a_captured_event():
    bus = EventBus()
    captures = collect(bus, topics.CAPTURE)
    victim = a_piece()

    BusPublisher(bus).on_capture(victim, 2500)

    assert len(captures) == 1
    assert captures[0].victim is victim
    assert captures[0].at_ms == 2500


def test_cooldown_done_callback_publishes_a_cooldown_done_event():
    bus = EventBus()
    done = collect(bus, topics.COOLDOWN_DONE)
    piece = a_piece()

    BusPublisher(bus).on_cooldown_done(piece, 3500)

    assert len(done) == 1
    assert (done[0].piece, done[0].at_ms) == (piece, 3500)


def test_game_over_callback_publishes_the_winner():
    """The winner used to be dropped here; with no snapshot every tick, it is all the
    far side gets."""
    bus = EventBus()
    overs = collect(bus, topics.GAME_OVER)

    BusPublisher(bus).on_game_over(Color.BLACK)

    assert len(overs) == 1
    assert overs[0].winner is Color.BLACK
