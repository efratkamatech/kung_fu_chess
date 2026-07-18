from kfchess.app.bootstrap import build_game
from kfchess.config import BOARD_CSV
from kfchess.graphics.assets import load_board_csv
from kfchess.graphics.img import Img
from kfchess.graphics.input import ClickFeedback, MouseInput, window_to_board
from kfchess.model.piece import PieceState
from kfchess.model.position import Position


# --- pure pixel scaling ------------------------------------------------------

def test_scales_window_pixels_to_board_pixels():
    # A window shown at twice the board size halves click coordinates.
    assert window_to_board(800, 800, (1600, 1600), (800, 800)) == (400, 400)


def test_identity_when_window_equals_board():
    assert window_to_board(150, 750, (800, 800), (800, 800)) == (150, 750)


def test_passes_through_when_window_size_unknown():
    assert window_to_board(150, 750, (0, 0), (800, 800)) == (150, 750)


# --- red-flash feedback ------------------------------------------------------

def test_click_feedback_reports_the_cell_until_it_expires():
    live = ClickFeedback(duration_s=999)
    assert live.current() is None
    live.flash(Position(2, 3))
    assert live.current() == Position(2, 3)

    expired = ClickFeedback(duration_s=0)  # elapses immediately
    expired.flash(Position(1, 1))
    assert expired.current() is None


# --- mouse routing (window size stubbed so scaling is identity) --------------

def a_mouse(monkeypatch):
    monkeypatch.setattr(Img, "window_image_size", staticmethod(lambda name: (800, 800)))
    engine, controller = build_game(load_board_csv(BOARD_CSV))
    feedback = ClickFeedback(duration_s=999)
    mouse = MouseInput(controller, "win", (800, 800), board_x_offset=0, feedback=feedback)
    return engine, controller, mouse, feedback


def test_left_click_selects_a_piece(monkeypatch):
    engine, controller, mouse, _ = a_mouse(monkeypatch)
    mouse._on_mouse(Img.MOUSE_LEFT_DOWN, 150, 750, 0, None)  # white knight on b1
    assert controller.selected_cell == Position(7, 1)


def test_clicking_the_selected_piece_again_makes_it_jump(monkeypatch):
    engine, controller, mouse, _ = a_mouse(monkeypatch)
    mouse._on_mouse(Img.MOUSE_LEFT_DOWN, 150, 750, 0, None)  # select b1
    mouse._on_mouse(Img.MOUSE_LEFT_DOWN, 150, 750, 0, None)  # click it again -> jump
    assert engine.board.piece_at(Position(7, 1)).state is PieceState.JUMPING
    assert controller.selected_cell is None


def test_clicking_an_unreachable_cell_flashes_it_red(monkeypatch):
    engine, controller, mouse, feedback = a_mouse(monkeypatch)
    mouse._on_mouse(Img.MOUSE_LEFT_DOWN, 150, 750, 0, None)  # select b1
    mouse._on_mouse(Img.MOUSE_LEFT_DOWN, 450, 450, 0, None)  # (4,4) is unreachable
    assert feedback.current() == Position(4, 4)


def test_right_click_jumps_the_clicked_piece(monkeypatch):
    engine, controller, mouse, _ = a_mouse(monkeypatch)
    mouse._on_mouse(Img.MOUSE_RIGHT_DOWN, 150, 750, 0, None)  # right-click b1
    assert engine.board.piece_at(Position(7, 1)).state is PieceState.JUMPING


def test_non_button_events_are_ignored(monkeypatch):
    engine, controller, mouse, _ = a_mouse(monkeypatch)
    mouse._on_mouse(0, 150, 750, 0, None)  # e.g. a mouse-move: neither left nor right down
    assert controller.selected_cell is None

