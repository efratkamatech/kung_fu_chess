"""End-to-end M1 check: a real game drives scores, log, and banner through the bus.

Unlike the isolated unit tests, this wires the *real* engine (via build_game) to a
BusPublisher and the three subscribers, then plays actual moves and asserts the whole
chain reacts: engine -> BusPublisher -> EventBus -> ScoreBoard / MovesLog / GameBanner.
"""

from kfchess.app.bootstrap import build_game
from kfchess.bus.event_bus import EventBus
from kfchess.bus.events import GameStarted
from kfchess.bus.publisher import BusPublisher
from kfchess.observers import GameBanner, MovesLog, ScoreBoard
from kfchess.model.board import Board
from kfchess.model.color import Color
from kfchess.model.piece import Piece
from kfchess.model.piece_type import standard_piece_types
from kfchess.model.position import Position


def wired_game(top_piece_letter):
    """A 3x1 board: a white rook at the bottom, ``top_piece_letter`` (black) at the top.

    Returns the engine plus the three subscribers, with the bus already announcing that
    the game has started.
    """
    reg = standard_piece_types()
    grid = [
        [Piece(reg.get(top_piece_letter), Color.BLACK)],
        [None],
        [Piece(reg.get("R"), Color.WHITE)],
    ]
    engine, _ = build_game(Board.from_grid(grid))
    bus = EventBus()
    engine.add_observer(BusPublisher(bus))
    score, log, banner = ScoreBoard(), MovesLog(3), GameBanner()
    score.subscribe(bus)
    log.subscribe(bus)
    banner.subscribe(bus)
    bus.publish(GameStarted())
    return engine, score, log, banner


def test_a_capture_updates_score_and_log_and_dismisses_the_start_banner():
    engine, score, log, banner = wired_game("Q")  # black queen at the top
    assert banner.show_start  # the start overlay is up before anyone moves

    engine.request_move(Position(2, 0), Position(0, 0))  # white rook -> black queen
    assert not banner.show_start  # the first move dismissed the start overlay

    engine.wait(3000)  # rook arrives (2 cells -> 2000 ms) and captures the queen
    assert score.score(Color.WHITE) == 9  # a queen is worth 9
    assert log.recent(Color.WHITE, 5) == ["wR a1 -> a3", "x bQ"]
    assert not banner.is_over  # a queen is not a king; the game continues


def test_capturing_the_king_ends_the_game_and_raises_the_over_banner():
    engine, score, log, banner = wired_game("K")  # black king at the top

    engine.request_move(Position(2, 0), Position(0, 0))  # white rook -> black king
    engine.wait(3000)  # rook arrives and captures the king

    assert banner.is_over  # the game-over overlay is now up
    assert engine.winner is Color.WHITE
    assert "x bK" in log.recent(Color.WHITE, 5)
