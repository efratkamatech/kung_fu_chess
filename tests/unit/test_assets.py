from kfchess.graphics.assets import load_board_csv, piece_token, token_to_piece
from kfchess.model.color import Color
from kfchess.model.piece import Piece
from kfchess.model.piece_type import PieceType, standard_piece_types


def test_piece_token_composes_color_and_letter():
    assert piece_token(Piece(PieceType("K", "king"), Color.WHITE)) == "wK"
    assert piece_token(Piece(PieceType("P", "pawn"), Color.BLACK)) == "bP"


def test_token_to_piece_and_empty():
    reg = standard_piece_types()
    piece = token_to_piece("bR", reg)
    assert piece.color is Color.BLACK and piece.piece_type.letter == "R"
    assert token_to_piece("", reg) is None
    assert token_to_piece("  ", reg) is None


def test_load_board_csv_builds_board_with_empty_rows(tmp_path):
    csv = tmp_path / "b.csv"
    csv.write_text("wK,bK\n,\n", encoding="utf-8")  # row of two empty cells kept
    board = load_board_csv(csv)
    from kfchess.model.position import Position

    assert (board.rows, board.cols) == (2, 2)
    assert piece_token(board.piece_at(Position(0, 0))) == "wK"
    assert board.piece_at(Position(1, 0)) is None
