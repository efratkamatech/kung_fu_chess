from kfchess.engine.clock import Clock
from kfchess.engine.game_engine import GameEngine
from kfchess.model.board import Board
from kfchess.model.color import Color
from kfchess.model.piece import Piece
from kfchess.model.piece_type import PieceType
from kfchess.model.position import Position


def make_piece():
    return Piece(PieceType("K", "king"), Color.WHITE)


def test_board_property_exposes_the_board():
    board = Board(2, 2)
    assert GameEngine(board, Clock()).board is board


def test_request_move_relocates_piece():
    board = Board(3, 3)
    piece = make_piece()
    board.place(Position(0, 0), piece)
    GameEngine(board, Clock()).request_move(Position(0, 0), Position(1, 1))
    assert board.is_empty(Position(0, 0))
    assert board.piece_at(Position(1, 1)) is piece


def test_request_move_from_empty_source_does_nothing():
    board = Board(2, 2)
    GameEngine(board, Clock()).request_move(Position(0, 0), Position(1, 1))
    assert board.is_empty(Position(1, 1))


def test_wait_advances_the_clock():
    clock = Clock()
    GameEngine(Board(2, 2), clock).wait(750)
    assert clock.now_ms == 750
