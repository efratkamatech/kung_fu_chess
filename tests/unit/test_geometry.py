from kfchess.graphics.geometry import board_pixel_size
from kfchess.model.board import Board


def test_board_pixel_size_is_cols_by_rows_times_cell():
    assert board_pixel_size(Board(3, 5), 100) == (500, 300)  # (cols*cell, rows*cell)
