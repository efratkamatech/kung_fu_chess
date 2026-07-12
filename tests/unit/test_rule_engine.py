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
    board = board_with("Z", at=(1, 1))  # no movement rule registered for "Z"
    assert not rule_engine().is_legal_move(board, Position(1, 1), Position(0, 1))


def place(board, letter, color, at):
    board.place(Position(*at), Piece(PieceType(letter, "x"), color))


def test_can_capture_an_enemy_at_the_destination():
    board = Board(1, 3)
    place(board, "R", Color.WHITE, (0, 0))
    place(board, "R", Color.BLACK, (0, 2))  # enemy on the destination
    assert rule_engine().is_legal_move(board, Position(0, 0), Position(0, 2))


def test_cannot_land_on_a_friendly_piece():
    board = Board(1, 2)
    place(board, "R", Color.WHITE, (0, 0))
    place(board, "P", Color.WHITE, (0, 1))  # friendly on the destination
    assert not rule_engine().is_legal_move(board, Position(0, 0), Position(0, 1))


def test_blocked_path_is_illegal():
    board = Board(1, 3)
    place(board, "R", Color.WHITE, (0, 0))
    place(board, "P", Color.WHITE, (0, 1))  # blocker in the path
    assert not rule_engine().is_legal_move(board, Position(0, 0), Position(0, 2))


def test_white_pawn_forward_to_empty_is_legal():
    board = board_with("P", color=Color.WHITE, at=(1, 1))
    assert rule_engine().is_legal_move(board, Position(1, 1), Position(0, 1))


def test_white_pawn_forward_onto_enemy_is_illegal():
    board = board_with("P", color=Color.WHITE, at=(1, 1))
    place(board, "R", Color.BLACK, (0, 1))  # enemy directly ahead
    assert not rule_engine().is_legal_move(board, Position(1, 1), Position(0, 1))
