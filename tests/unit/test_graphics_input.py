from kfchess.graphics.input import window_to_board


def test_scales_window_pixels_to_board_pixels():
    # A window shown at twice the board size halves click coordinates.
    assert window_to_board(800, 800, (1600, 1600), (800, 800)) == (400, 400)


def test_identity_when_window_equals_board():
    assert window_to_board(150, 750, (800, 800), (800, 800)) == (150, 750)


def test_passes_through_when_window_size_unknown():
    assert window_to_board(150, 750, (0, 0), (800, 800)) == (150, 750)
