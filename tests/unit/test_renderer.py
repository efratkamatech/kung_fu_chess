import numpy as np

from kfchess.config import BOARD_CSV, BOARD_IMAGE, CELL_PX, PANEL_PX, PIECES_DIR
from kfchess.engine.arbiter import MovingPiece
from kfchess.graphics.assets import AnimationBank, load_board_csv
from kfchess.graphics.events import MovesLog, ScoreBoard
from kfchess.graphics.hud import Hud
from kfchess.graphics.renderer import BoardRenderer
from kfchess.model.board import Board
from kfchess.model.color import Color
from kfchess.model.piece import Piece, PieceState
from kfchess.model.piece_type import standard_piece_types
from kfchess.model.position import Position


def a_renderer(**kwargs):
    return BoardRenderer(BOARD_IMAGE, AnimationBank(PIECES_DIR, CELL_PX), CELL_PX, **kwargs)


def a_piece(letter, color=Color.WHITE):
    return Piece(standard_piece_types().get(letter), color)


def cell(img, row, col, x_offset=0):
    a = img.img
    y0, x0 = row * CELL_PX, col * CELL_PX + x_offset
    return a[y0 : y0 + CELL_PX, x0 : x0 + CELL_PX, :3].astype(int)


def test_render_board_only_has_board_pixel_size():
    frame = a_renderer().render(load_board_csv(BOARD_CSV))
    assert (frame.width, frame.height) == (8 * CELL_PX, 8 * CELL_PX)


def test_render_with_two_panels_sizes_the_full_canvas():
    frame = a_renderer(left_panel_px=PANEL_PX, right_panel_px=PANEL_PX).render(Board(8, 8))
    assert frame.width == PANEL_PX + 8 * CELL_PX + PANEL_PX
    assert frame.height == 8 * CELL_PX


def test_a_settled_piece_is_drawn_into_its_cell():
    renderer = a_renderer()
    empty = cell(renderer.render(Board(8, 8)), 3, 3)
    board = Board(8, 8)
    board.place(Position(3, 3), a_piece("Q"))
    drawn = cell(renderer.render(board), 3, 3)
    assert not np.array_equal(empty, drawn)


def test_a_moving_piece_is_drawn_at_its_interpolated_cell():
    renderer = a_renderer()
    base = cell(renderer.render(Board(8, 8)), 3, 3)
    mover = MovingPiece(a_piece("N"), (3.0, 3.0), Position(1, 1), Position(3, 3))
    drawn = cell(renderer.render(Board(8, 8), moving_pieces=[mover]), 3, 3)
    assert not np.array_equal(base, drawn)


def test_legal_targets_tint_a_cell_green():
    renderer = a_renderer()
    hinted = cell(renderer.render(Board(8, 8), legal_targets=[Position(4, 4)]), 4, 4)
    g, r, b = hinted[:, :, 1].mean(), hinted[:, :, 2].mean(), hinted[:, :, 0].mean()
    assert g >= r and g >= b  # green is the dominant channel in a hinted cell


def test_selected_cell_gets_a_green_outline():
    renderer = a_renderer()
    outlined = cell(renderer.render(Board(8, 8), selected=Position(2, 2)), 2, 2)
    assert (outlined[:, :, 1] - outlined[:, :, 2]).max() > 100  # a strong green pixel


def test_invalid_cell_gets_a_red_outline():
    renderer = a_renderer()
    flashed = cell(renderer.render(Board(8, 8), invalid_cell=Position(6, 1)), 6, 1)
    assert (flashed[:, :, 2] - flashed[:, :, 1]).max() > 100  # a strong red pixel


def test_cooldown_gauge_changes_the_cooling_cell():
    renderer = a_renderer()
    piece = a_piece("R")
    piece.state = PieceState.COOLDOWN
    board = Board(8, 8)
    board.place(Position(5, 5), piece)
    without = cell(renderer.render(board), 5, 5)
    withgauge = cell(renderer.render(board, cooldowns={piece: 0.8}), 5, 5)
    assert not np.array_equal(without, withgauge)


def test_game_over_dims_the_board_area():
    renderer = a_renderer(left_panel_px=PANEL_PX, right_panel_px=PANEL_PX)
    frame = renderer.render(load_board_csv(BOARD_CSV))
    before = cell(frame, 4, 4, x_offset=PANEL_PX).mean()
    renderer.draw_game_over(frame, "Efrat wins!", "[N] New Game    [Esc] Quit")
    after = cell(frame, 4, 4, x_offset=PANEL_PX).mean()
    assert after < before  # the board is darkened behind the banner


def test_start_banner_dims_the_board_area():
    renderer = a_renderer(left_panel_px=PANEL_PX, right_panel_px=PANEL_PX)
    frame = renderer.render(load_board_csv(BOARD_CSV))
    before = cell(frame, 4, 4, x_offset=PANEL_PX).mean()
    renderer.draw_start_banner(frame, "KungFu Chess", "Click a piece to begin")
    after = cell(frame, 4, 4, x_offset=PANEL_PX).mean()
    assert after < before  # the board is lightly darkened behind the start banner


def test_render_draws_the_hud_panel():
    board = Board(8, 8)
    hud = Hud("Efrat", Color.WHITE, MovesLog(8), ScoreBoard(), left_x=8 * CELL_PX + 10)
    with_hud = a_renderer(huds=(hud,), right_panel_px=PANEL_PX).render(board)
    without = a_renderer(right_panel_px=PANEL_PX).render(board)
    panel = np.s_[:, 8 * CELL_PX :, :]  # the right panel region
    assert not np.array_equal(with_hud.img[panel], without.img[panel])


def test_a_finished_cooldown_draws_no_gauge():
    renderer = a_renderer()
    piece = a_piece("R")
    piece.state = PieceState.COOLDOWN
    board = Board(8, 8)
    board.place(Position(5, 5), piece)
    without = cell(renderer.render(board), 5, 5)
    finished = cell(renderer.render(board, cooldowns={piece: 0.0}), 5, 5)  # remaining 0
    assert np.array_equal(without, finished)
