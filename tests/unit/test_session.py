"""Tests for GameSession: colour assignment, move handling, and snapshots."""

from kfchess.config import SOUND_CAPTURE, SOUND_GAME_OVER, SOUND_GAME_START, SOUND_MOVE
from kfchess.model.board import Board
from kfchess.model.color import Color
from kfchess.model.piece import Piece
from kfchess.model.piece_type import standard_piece_types
from kfchess.server.session import GameSession
from kfchess.snapshot import CellView


def rook_session():
    """A 3x3 board with a lone white rook at a1 (bottom-left)."""
    reg = standard_piece_types()
    grid = [
        [None, None, None],
        [None, None, None],
        [Piece(reg.get("R"), Color.WHITE), None, None],
    ]
    return GameSession(Board.from_grid(grid))


def king_session():
    """A 3x3 board: white rook at a1, black king at a3 (same file, capturable)."""
    reg = standard_piece_types()
    grid = [
        [Piece(reg.get("K"), Color.BLACK), None, None],
        [None, None, None],
        [Piece(reg.get("R"), Color.WHITE), None, None],
    ]
    return GameSession(Board.from_grid(grid))


# --- colour assignment -------------------------------------------------------

def test_first_joiner_is_white_second_is_black_third_is_refused():
    session = rook_session()
    assert session.assign_color() is Color.WHITE
    assert session.assign_color() is Color.BLACK
    assert session.assign_color() is None  # only two players


# --- applying commands -------------------------------------------------------

def test_a_legal_command_from_the_right_player_is_accepted():
    session = rook_session()
    assert session.apply_command(Color.WHITE, "WRa1a3") is None  # a1 -> a3, up the file


def test_a_command_for_the_other_colour_is_refused():
    session = rook_session()
    assert session.apply_command(Color.WHITE, "BRa1a3") == "not_your_colour"


def test_moving_a_piece_that_is_not_yours_is_refused():
    session = rook_session()  # a1 holds a *white* rook
    assert session.apply_command(Color.BLACK, "BRa1a3") == "not_your_piece"


def test_moving_from_an_empty_square_is_refused():
    session = rook_session()
    assert session.apply_command(Color.WHITE, "WRb2b3") == "empty_source"


def test_a_wrong_piece_letter_is_refused():
    session = rook_session()  # a1 is a rook, not a queen
    assert session.apply_command(Color.WHITE, "WQa1a3") == "wrong_piece"


def test_an_illegal_move_is_refused():
    session = rook_session()
    assert session.apply_command(Color.WHITE, "WRa1b2") == "illegal_move"  # rooks don't go diagonal


def test_a_malformed_command_is_refused_with_a_reason():
    session = rook_session()
    assert session.apply_command(Color.WHITE, "junk!!") is not None


# --- snapshots ---------------------------------------------------------------

def test_a_fresh_snapshot_shows_the_start_phase_and_the_pieces():
    snapshot = rook_session().snapshot()
    assert snapshot.phase == "start"
    assert snapshot.winner is None
    assert snapshot.cells[2][0] == CellView("wR", "IDLE", 0.0)
    assert snapshot.moving == []


def test_a_moving_piece_appears_in_the_moving_overlay_not_the_cells():
    session = rook_session()
    session.apply_command(Color.WHITE, "WRa1a3")  # start the motion
    snapshot = session.snapshot()
    assert snapshot.phase == "playing"          # the first move dismissed the start phase
    assert snapshot.cells[2][0] is None         # the origin cell is now empty of a settled piece
    assert len(snapshot.moving) == 1
    assert snapshot.moving[0].token == "wR"


def test_capturing_the_king_is_reflected_in_the_snapshot():
    session = king_session()
    session.apply_command(Color.WHITE, "WRa1a3")  # rook -> king
    session.tick(100000)                          # rook arrives and captures
    snapshot = session.snapshot()
    assert snapshot.phase == "over"
    assert snapshot.winner is Color.WHITE
    assert "x bK" in snapshot.logs[Color.WHITE]


# --- immediate-reaction events (sound) ----------------------------------------

def test_game_started_is_queued_as_soon_as_the_session_is_built():
    session = rook_session()
    assert session.drain_events() == [SOUND_GAME_START]


def test_drain_events_clears_the_queue():
    session = rook_session()
    session.drain_events()
    assert session.drain_events() == []  # nothing left the second time


def test_a_move_queues_a_move_sound():
    session = rook_session()
    session.drain_events()  # clear the initial game-start event
    session.apply_command(Color.WHITE, "WRa1a3")
    assert session.drain_events() == [SOUND_MOVE]


def test_an_illegal_move_queues_no_event():
    session = rook_session()
    session.drain_events()
    session.apply_command(Color.WHITE, "WRa1b2")  # rejected: illegal
    assert session.drain_events() == []


def test_capturing_the_king_queues_capture_then_game_over():
    session = king_session()
    session.drain_events()  # clear the initial game-start event
    session.apply_command(Color.WHITE, "WRa1a3")
    session.drain_events()  # clear the move event
    session.tick(100000)    # rook arrives and captures the king
    assert session.drain_events() == [SOUND_CAPTURE, SOUND_GAME_OVER]
