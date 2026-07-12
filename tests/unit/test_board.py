import pytest

from kfchess.model.board import Board
from kfchess.model.color import Color
from kfchess.model.piece import Piece
from kfchess.model.piece_type import PieceType
from kfchess.model.position import Position


def make_piece(letter="K", color=Color.WHITE):
    return Piece(PieceType(letter, "x"), color)


def test_dimensions_exposed_and_positive_enforced():
    board = Board(3, 4)
    assert board.rows == 3
    assert board.cols == 4
    with pytest.raises(ValueError):
        Board(0, 4)
    with pytest.raises(ValueError):
        Board(3, -1)


def test_in_bounds_all_edges():
    board = Board(2, 2)
    assert board.in_bounds(Position(0, 0))
    assert not board.in_bounds(Position(-1, 0))  # row below 0
    assert not board.in_bounds(Position(2, 0))   # row past the last
    assert not board.in_bounds(Position(0, -1))  # col below 0
    assert not board.in_bounds(Position(0, 2))   # col past the last


def test_place_and_query():
    board = Board(2, 2)
    piece = make_piece()
    board.place(Position(0, 0), piece)
    assert board.piece_at(Position(0, 0)) is piece
    assert not board.is_empty(Position(0, 0))
    assert board.is_empty(Position(1, 1))


def test_off_board_access_raises():
    board = Board(2, 2)
    with pytest.raises(ValueError):
        board.piece_at(Position(5, 5))
    with pytest.raises(ValueError):
        board.place(Position(5, 5), make_piece())


def test_from_grid_infers_dimensions_and_places_pieces():
    piece = make_piece()
    board = Board.from_grid([[piece, None], [None, None]])
    assert board.rows == 2
    assert board.cols == 2
    assert board.piece_at(Position(0, 0)) is piece
    assert board.is_empty(Position(0, 1))


def test_from_grid_rejects_empty():
    with pytest.raises(ValueError):
        Board.from_grid([])


def test_from_grid_rejects_ragged():
    with pytest.raises(ValueError):
        Board.from_grid([[None, None], [None]])
