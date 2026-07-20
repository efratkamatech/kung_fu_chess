"""Tests for the pub/sub EventBus and its event objects."""

from kfchess.bus import topics
from kfchess.bus.event_bus import EventBus
from kfchess.bus.events import Captured, GameOver, GameStarted, MoveStarted
from kfchess.model.color import Color
from kfchess.model.piece import Piece
from kfchess.model.piece_type import standard_piece_types
from kfchess.model.position import Position


def a_piece():
    return Piece(standard_piece_types().get("R"), Color.WHITE)


# --- the event objects -------------------------------------------------------

def test_each_event_carries_its_topic_and_payload():
    piece = a_piece()
    move = MoveStarted(piece, Position(1, 0), Position(3, 0))
    assert move.topic == topics.MOVE_STARTED
    assert (move.piece, move.source, move.target) == (piece, Position(1, 0), Position(3, 0))

    captured = Captured(piece)
    assert captured.topic == topics.CAPTURE
    assert captured.victim is piece

    assert GameStarted().topic == topics.GAME_STARTED

    over = GameOver(Color.WHITE)
    assert over.topic == topics.GAME_OVER
    assert over.winner is Color.WHITE
    assert GameOver().winner is None  # winner is optional (e.g. an abandoned game)


# --- the bus -----------------------------------------------------------------

def test_publish_delivers_the_event_to_a_subscriber():
    bus = EventBus()
    received = []
    bus.subscribe(topics.CAPTURE, received.append)

    event = Captured(a_piece())
    bus.publish(event)

    assert received == [event]


def test_publish_with_no_subscribers_is_a_no_op():
    bus = EventBus()
    bus.publish(GameStarted())  # must not raise, simply dropped


def test_multiple_handlers_fire_in_subscription_order():
    bus = EventBus()
    order = []
    bus.subscribe(topics.GAME_OVER, lambda e: order.append("first"))
    bus.subscribe(topics.GAME_OVER, lambda e: order.append("second"))

    bus.publish(GameOver(Color.BLACK))

    assert order == ["first", "second"]


def test_a_handler_only_receives_its_own_topic():
    bus = EventBus()
    captures, moves = [], []
    bus.subscribe(topics.CAPTURE, captures.append)
    bus.subscribe(topics.MOVE_STARTED, moves.append)

    bus.publish(Captured(a_piece()))

    assert len(captures) == 1
    assert moves == []  # the move-started handler was not touched
