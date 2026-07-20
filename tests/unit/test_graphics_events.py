from kfchess.bus.event_bus import EventBus
from kfchess.bus.events import Captured, MoveStarted
from kfchess.observers import MovesLog, ScoreBoard
from kfchess.model.color import Color
from kfchess.model.piece import Piece
from kfchess.model.piece_type import standard_piece_types
from kfchess.model.position import Position


def piece(letter, color):
    return Piece(standard_piece_types().get(letter), color)


def wired_log():
    """A MovesLog subscribed to a fresh bus, returned with that bus."""
    bus = EventBus()
    log = MovesLog(board_rows=8)
    log.subscribe(bus)
    return bus, log


def test_moves_log_splits_move_and_capture_by_side():
    bus, log = wired_log()
    bus.publish(MoveStarted(piece("N", Color.WHITE), Position(7, 1), Position(5, 2)))
    bus.publish(Captured(piece("P", Color.BLACK)))  # white captured a black pawn
    assert log.recent(Color.WHITE, 10) == ["wN b1 -> c3", "x bP"]
    assert log.recent(Color.BLACK, 10) == []


def test_moves_log_recent_limits_to_count():
    bus, log = wired_log()
    for _ in range(5):
        bus.publish(Captured(piece("P", Color.BLACK)))  # all credited to white
    assert len(log.recent(Color.WHITE, 3)) == 3


def test_scoreboard_credits_the_captor():
    bus = EventBus()
    score = ScoreBoard()
    score.subscribe(bus)
    bus.publish(Captured(piece("Q", Color.BLACK)))  # white captured a black queen
    assert score.score(Color.WHITE) == 9
    assert score.score(Color.BLACK) == 0
