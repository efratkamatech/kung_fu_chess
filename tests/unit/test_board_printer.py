from kfchess.model.board import Board
from kfchess.model.color import Color
from kfchess.model.piece import Piece
from kfchess.model.piece_type import PieceType
from kfchess.model.position import Position
from kfchess.text_io.board_printer import BoardPrinter


def test_renders_grid_only_with_pieces_and_empties():
    board = Board(2, 3)
    board.place(Position(0, 0), Piece(PieceType("K", "king"), Color.WHITE))
    board.place(Position(1, 2), Piece(PieceType("R", "rook"), Color.BLACK))
    assert BoardPrinter().render(board) == "wK . .\n. . bR"
