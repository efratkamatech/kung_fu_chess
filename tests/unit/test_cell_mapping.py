from kfchess.app.bootstrap import build_game
from kfchess.config import CELL_PX
from kfchess.model.board import Board
from kfchess.model.position import Position


def a_controller():
    _engine, controller = build_game(Board(8, 8))
    return controller


def test_every_corner_of_a_cell_maps_to_that_cell():
    controller = a_controller()
    for row in range(8):
        for col in range(8):
            x0, y0 = col * CELL_PX, row * CELL_PX
            corners = [
                (x0, y0),                                # top-left
                (x0 + CELL_PX - 1, y0),                  # top-right
                (x0, y0 + CELL_PX - 1),                  # bottom-left
                (x0 + CELL_PX - 1, y0 + CELL_PX - 1),    # bottom-right
            ]
            for x, y in corners:
                assert controller.cell_at(x, y) == Position(row, col)


def test_pixels_just_past_the_last_cell_fall_off_the_board():
    engine, controller = build_game(Board(8, 8))
    board = engine.board
    assert controller.cell_at(799, 799) == Position(7, 7)  # last pixel is still the board
    assert board.in_bounds(controller.cell_at(799, 799))
    assert not board.in_bounds(controller.cell_at(800, 0))  # one past the right edge
    assert not board.in_bounds(controller.cell_at(0, 800))  # one past the bottom edge
