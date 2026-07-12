from kfchess.engine.clock import Clock
from kfchess.engine.game_engine import GameEngine
from kfchess.model.board import Board
from kfchess.model.color import Color
from kfchess.model.piece import Piece
from kfchess.model.piece_type import PieceType
from kfchess.model.position import Position
from kfchess.movement.rules import standard_movement_rules
from kfchess.rules.rule_engine import RuleEngine


def make_engine(board):
    return GameEngine(board, Clock(), RuleEngine(standard_movement_rules()))


def rook_board():
    board = Board(3, 3)
    board.place(Position(0, 0), Piece(PieceType("R", "rook"), Color.WHITE))
    return board


def test_board_property_exposes_the_board():
    board = Board(2, 2)
    assert make_engine(board).board is board


def test_legal_move_relocates_piece():
    board = rook_board()
    make_engine(board).request_move(Position(0, 0), Position(0, 2))
    assert board.is_empty(Position(0, 0))
    assert board.piece_at(Position(0, 2)).piece_type.letter == "R"


def test_illegal_move_is_ignored():
    board = rook_board()
    make_engine(board).request_move(Position(0, 0), Position(1, 1))  # rook diagonal
    assert board.piece_at(Position(0, 0)).piece_type.letter == "R"   # stayed put
    assert board.is_empty(Position(1, 1))


def test_move_from_empty_source_does_nothing():
    board = Board(2, 2)
    make_engine(board).request_move(Position(0, 0), Position(0, 1))
    assert board.is_empty(Position(0, 1))


def test_wait_advances_the_clock():
    clock = Clock()
    GameEngine(Board(2, 2), clock, RuleEngine(standard_movement_rules())).wait(750)
    assert clock.now_ms == 750
