from kfchess.graphics.events import MovesLog, ScoreBoard
from kfchess.model.color import Color
from kfchess.model.piece import Piece
from kfchess.model.piece_type import PieceType, standard_piece_types
from kfchess.model.position import Position


def piece(letter, color):
    return Piece(standard_piece_types().get(letter), color)


def test_moves_log_records_move_and_capture_in_chess_squares():
    log = MovesLog(board_rows=8)
    log.on_move_started(piece("N", Color.WHITE), Position(7, 1), Position(5, 2))
    log.on_capture(piece("P", Color.BLACK))
    assert log.recent(10) == ["wN b1 -> c3", "x bP"]


def test_moves_log_recent_limits_to_count():
    log = MovesLog(board_rows=8)
    for _ in range(5):
        log.on_capture(piece("P", Color.BLACK))
    assert len(log.recent(3)) == 3


def test_scoreboard_credits_the_captor():
    score = ScoreBoard()
    score.on_capture(piece("Q", Color.BLACK))  # white captured a black queen
    assert score.score(Color.WHITE) == 9
    assert score.score(Color.BLACK) == 0
