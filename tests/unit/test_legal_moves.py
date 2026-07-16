from kfchess.app.bootstrap import build_game
from kfchess.config import BOARD_CSV
from kfchess.control.controller import ClickOutcome
from kfchess.graphics.assets import load_board_csv
from kfchess.model.position import Position


def a_game():
    return build_game(load_board_csv(BOARD_CSV))


def test_legal_targets_for_opening_knight():
    engine, _ = a_game()
    targets = {(p.row, p.col) for p in engine.legal_targets(Position(7, 1))}
    assert targets == {(5, 0), (5, 2)}  # a3 and c3 (d2 is blocked by its own pawn)


def test_request_move_reports_success():
    engine, _ = a_game()
    assert engine.request_move(Position(7, 1), Position(4, 4)) is False  # illegal
    assert engine.request_move(Position(7, 1), Position(5, 2)) is True   # legal


def test_click_illegal_target_returns_illegal_outcome():
    engine, controller = a_game()
    assert controller.click(150, 750) is ClickOutcome.SELECTED    # select knight b1
    assert controller.click(450, 450) is ClickOutcome.ILLEGAL     # unreachable cell (4,4)
