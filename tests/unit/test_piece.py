from kfchess.model.color import Color
from kfchess.model.piece import Piece, PieceState
from kfchess.model.piece_type import PieceType


def test_defaults_to_idle():
    piece = Piece(PieceType("K", "king"), Color.WHITE)
    assert piece.state is PieceState.IDLE


def test_stores_identity_and_accepts_explicit_state():
    piece = Piece(PieceType("R", "rook"), Color.BLACK, PieceState.IDLE)
    assert piece.piece_type.letter == "R"
    assert piece.color is Color.BLACK
    assert piece.state is PieceState.IDLE


def test_repr_is_readable():
    piece = Piece(PieceType("R", "rook"), Color.BLACK)
    assert repr(piece) == "Piece('R', BLACK, IDLE)"


def test_compared_by_identity_not_by_fields():
    kind = PieceType("P", "pawn")
    a = Piece(kind, Color.WHITE)
    b = Piece(kind, Color.WHITE)
    assert a != b  # two distinct pawns are different pieces
    assert a == a
