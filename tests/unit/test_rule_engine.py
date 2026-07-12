from kfchess.model.board import Board
from kfchess.model.color import Color
from kfchess.model.piece import Piece
from kfchess.model.piece_type import PieceType
from kfchess.model.position import Position
from kfchess.movement.rules import standard_movement_rules
from kfchess.rules.rule_engine import RuleEngine


def rule_engine():
    return RuleEngine(standard_movement_rules())


def board_with(letter, color=Color.WHITE, at=(0, 0), size=(3, 3)):
    board = Board(*size)
    board.place(Position(*at), Piece(PieceType(letter, "x"), color))
    return board


def test_legal_shape_is_allowed():
    board = board_with("R", at=(0, 0))
    assert rule_engine().is_legal_move(board, Position(0, 0), Position(0, 2))


def test_illegal_shape_is_rejected():
    board = board_with("R", at=(0, 0))
    assert not rule_engine().is_legal_move(board, Position(0, 0), Position(1, 1))


def test_empty_source_is_illegal():
    board = Board(3, 3)
    assert not rule_engine().is_legal_move(board, Position(0, 0), Position(0, 1))


def test_piece_without_a_rule_cannot_move():
    board = board_with("P", at=(1, 1))  # pawn has no movement rule yet (Iteration 5)
    assert not rule_engine().is_legal_move(board, Position(1, 1), Position(0, 1))
