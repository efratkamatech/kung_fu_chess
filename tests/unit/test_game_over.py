from kfchess.app.bootstrap import build_game
from kfchess.model.board import Board
from kfchess.model.color import Color
from kfchess.model.piece import Piece
from kfchess.model.piece_type import standard_piece_types
from kfchess.model.position import Position


def test_capturing_a_king_ends_the_game_and_records_the_winner():
    reg = standard_piece_types()
    grid = [[Piece(reg.get("K"), Color.BLACK)], [None], [Piece(reg.get("R"), Color.WHITE)]]
    engine, _ = build_game(Board.from_grid(grid))

    assert engine.is_game_over is False
    assert engine.winner is None

    engine.request_move(Position(2, 0), Position(0, 0))  # rook captures the king
    engine.wait(100000)

    assert engine.is_game_over is True
    assert engine.winner is Color.WHITE
