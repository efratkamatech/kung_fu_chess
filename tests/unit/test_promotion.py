from kfchess.model.board import Board
from kfchess.model.color import Color
from kfchess.model.piece import Piece
from kfchess.model.piece_type import PieceType
from kfchess.model.position import Position
from kfchess.movement.rules import PAWN_FORWARD
from kfchess.rules.promotion import Promotion

QUEEN = PieceType("Q", "queen")


def promotion():
    return Promotion(PAWN_FORWARD, QUEEN)


def white_pawn():
    return Piece(PieceType("P", "pawn", is_pawn=True), Color.WHITE)


def black_pawn():
    return Piece(PieceType("P", "pawn", is_pawn=True), Color.BLACK)


def test_white_pawn_promoted_on_the_top_row():
    pawn = white_pawn()
    promotion().apply(pawn, Position(0, 1), Board(3, 3))  # white far row = 0
    assert pawn.piece_type.letter == "Q"


def test_black_pawn_promoted_on_the_bottom_row():
    pawn = black_pawn()
    promotion().apply(pawn, Position(2, 1), Board(3, 3))  # black far row = rows - 1
    assert pawn.piece_type.letter == "Q"


def test_pawn_not_on_the_far_row_is_not_promoted():
    pawn = white_pawn()
    promotion().apply(pawn, Position(1, 1), Board(3, 3))  # not the far row
    assert pawn.piece_type.letter == "P"


def test_a_non_pawn_on_the_far_row_is_not_promoted():
    rook = Piece(PieceType("R", "rook"), Color.WHITE)
    promotion().apply(rook, Position(0, 1), Board(3, 3))
    assert rook.piece_type.letter == "R"
