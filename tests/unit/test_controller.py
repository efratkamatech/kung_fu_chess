from kfchess.control.controller import Controller
from kfchess.engine.clock import Clock
from kfchess.engine.game_engine import GameEngine
from kfchess.model.board import Board
from kfchess.model.color import Color
from kfchess.model.piece import Piece
from kfchess.model.piece_type import PieceType
from kfchess.model.position import Position


def piece(color=Color.WHITE, letter="K"):
    return Piece(PieceType(letter, "x"), color)


def setup(board):
    controller = Controller(GameEngine(board, Clock()))
    return board, controller


def test_select_then_move_via_center_clicks():
    board, controller = setup(Board(3, 3))
    board.place(Position(0, 0), piece())
    controller.click(50, 50)     # center of (0,0) -> select
    controller.click(150, 150)   # center of (1,1) empty -> move there
    assert board.is_empty(Position(0, 0))
    assert board.piece_at(Position(1, 1)) is not None


def test_off_board_click_is_ignored():
    board, controller = setup(Board(2, 2))
    board.place(Position(0, 0), piece())
    controller.click(9999, 9999)  # far outside -> ignored (no selection made)
    controller.click(150, 150)    # empty cell, still no selection -> ignored
    assert board.piece_at(Position(0, 0)) is not None


def test_click_empty_with_no_selection_is_ignored():
    board, controller = setup(Board(2, 2))
    controller.click(50, 50)      # empty, nothing selected
    controller.click(150, 150)    # empty, still nothing selected
    assert board.is_empty(Position(0, 0))
    assert board.is_empty(Position(1, 1))


def test_clicking_a_friendly_piece_replaces_the_selection():
    board, controller = setup(Board(1, 3))
    a = piece(Color.WHITE, "K")
    b = piece(Color.WHITE, "R")
    board.place(Position(0, 0), a)
    board.place(Position(0, 1), b)
    controller.click(50, 50)    # select a at (0,0)
    controller.click(150, 50)   # friendly b at (0,1) -> selection switches to b
    controller.click(250, 50)   # empty (0,2) -> the *selected* (b) moves there
    assert board.piece_at(Position(0, 0)) is a   # a never moved
    assert board.is_empty(Position(0, 1))        # b left its cell
    assert board.piece_at(Position(0, 2)) is b   # b moved


def test_move_onto_enemy_relocates_over_it():
    board, controller = setup(Board(1, 2))
    white = piece(Color.WHITE)
    black = piece(Color.BLACK)
    board.place(Position(0, 0), white)
    board.place(Position(0, 1), black)
    controller.click(50, 50)    # select white
    controller.click(150, 50)   # enemy cell -> move request (not a friendly swap)
    assert board.is_empty(Position(0, 0))
    assert board.piece_at(Position(0, 1)) is white
