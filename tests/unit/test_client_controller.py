"""Tests for the client-side selection controller (click -> command)."""

from kfchess.client.controller import ClientController
from kfchess.model.color import Color
from kfchess.model.position import Position
from kfchess.snapshot import CellView, GameSnapshot


def snapshot_with(cells):
    return GameSnapshot(
        rows=2,
        cols=2,
        cells=cells,
        moving=[],
        scores={Color.WHITE: 0, Color.BLACK: 0},
        logs={Color.WHITE: [], Color.BLACK: []},
        phase="playing",
        winner=None,
        now_ms=0,
    )


def board_white_rook_black_king():
    # white rook at (1,0)=a1, black king at (0,1)=b2
    return snapshot_with(
        [
            [None, CellView("bK", "IDLE")],
            [CellView("wR", "IDLE"), None],
        ]
    )


def test_a_spectator_selects_nothing():
    controller = ClientController()
    assert controller.click(Position(1, 0), board_white_rook_black_king(), None) is None
    assert controller.selected is None


def test_clicking_your_own_piece_selects_it():
    controller = ClientController()
    assert controller.click(Position(1, 0), board_white_rook_black_king(), Color.WHITE) is None
    assert controller.selected == Position(1, 0)


def test_selecting_then_clicking_a_target_builds_the_command():
    controller = ClientController()
    snapshot = board_white_rook_black_king()
    controller.click(Position(1, 0), snapshot, Color.WHITE)          # select the rook at a1
    command = controller.click(Position(0, 0), snapshot, Color.WHITE)  # move to a2
    assert command == "WRa1a2"
    assert controller.selected is None                               # selection cleared


def test_selecting_then_clicking_an_enemy_builds_a_capture_command():
    controller = ClientController()
    snapshot = board_white_rook_black_king()
    controller.click(Position(1, 0), snapshot, Color.WHITE)          # select rook a1
    assert controller.click(Position(0, 1), snapshot, Color.WHITE) == "WRa1b2"  # capture king


def test_clicking_another_of_your_pieces_switches_the_selection():
    two_rooks = snapshot_with(
        [[CellView("wR", "IDLE"), None], [CellView("wR", "IDLE"), None]]
    )
    controller = ClientController()
    controller.click(Position(0, 0), two_rooks, Color.WHITE)
    assert controller.click(Position(1, 0), two_rooks, Color.WHITE) is None  # switched
    assert controller.selected == Position(1, 0)


def test_clicking_an_enemy_piece_first_does_nothing():
    controller = ClientController()
    assert controller.click(Position(0, 1), board_white_rook_black_king(), Color.WHITE) is None
    assert controller.selected is None


def test_an_off_board_click_is_ignored():
    controller = ClientController()
    assert controller.click(Position(9, 9), board_white_rook_black_king(), Color.WHITE) is None


def test_a_stale_selection_is_dropped_when_the_piece_is_gone():
    controller = ClientController()
    controller.click(Position(1, 0), board_white_rook_black_king(), Color.WHITE)  # select a1
    # a new snapshot where the rook has left a1 (e.g. it moved); the cell is now empty
    moved = snapshot_with([[None, CellView("bK", "IDLE")], [None, None]])
    assert controller.click(Position(0, 0), moved, Color.WHITE) is None  # selection dropped
    assert controller.selected is None
