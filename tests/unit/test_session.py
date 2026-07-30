"""Tests for GameSession: colour assignment, move handling, and snapshots."""

from kfchess.config import (
    COOLDOWN_MS,
    MS_PER_CELL,
    RESIGN_COUNTDOWN_MS,
    SOUND_CAPTURE,
    SOUND_GAME_OVER,
    SOUND_GAME_START,
    SOUND_MOVE,
)
from kfchess.model.board import Board
from kfchess.model.color import Color
from kfchess.model.piece import Piece
from kfchess.model.piece_type import standard_piece_types
from kfchess.server.session import GameSession
from kfchess.shared.protocol import (
    Captured,
    CooldownDone,
    Disconnected,
    Event,
    GameOver,
    MoveStarted,
    Reconnected,
    Settled,
)
from kfchess.shared.snapshot import CellView


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


# --- names ---------------------------------------------------------------------

def test_a_fresh_session_has_no_names_yet():
    assert rook_session().snapshot().names == {}


def test_set_name_records_a_players_name_by_colour():
    session = rook_session()
    session.set_name(Color.WHITE, "Efrat")
    assert session.snapshot().names == {Color.WHITE: "Efrat"}


def test_only_the_colours_that_logged_in_appear_in_names():
    session = rook_session()
    session.set_name(Color.WHITE, "Efrat")
    session.set_name(Color.BLACK, "Dan")
    assert session.snapshot().names == {Color.WHITE: "Efrat", Color.BLACK: "Dan"}


def test_a_fresh_session_has_no_ratings_yet():
    assert rook_session().snapshot().ratings == {}


def test_set_rating_records_a_rating_by_colour():
    session = rook_session()
    session.set_rating(Color.WHITE, 1234)
    assert session.snapshot().ratings == {Color.WHITE: 1234}


def test_a_matchmade_game_has_no_room_id():
    assert rook_session().snapshot().room_id is None


def test_set_room_id_is_reflected_in_the_snapshot():
    session = rook_session()
    session.set_room_id("7C2F")
    assert session.snapshot().room_id == "7C2F"


# --- snapshots ---------------------------------------------------------------

def test_a_fresh_snapshot_shows_the_start_phase_and_the_pieces():
    snapshot = rook_session().snapshot()
    assert snapshot.phase == "start"
    assert snapshot.winner is None
    assert snapshot.cells[2][0] == CellView("wR", "IDLE", 0.0, piece_id=0)
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


# --- deltas: what actually happened, instead of a picture of everything -------

def test_game_started_is_queued_as_soon_as_the_session_is_built():
    session = rook_session()
    assert session.drain_deltas() == [Event(SOUND_GAME_START)]


def test_draining_clears_the_queue():
    session = rook_session()
    session.drain_deltas()
    assert session.drain_deltas() == []  # nothing left the second time


def test_a_move_queues_its_sound_and_a_move_started_delta():
    """A 2-cell move on a 3-row board: leaves a1 at 0, due at a3 at 2 x MS_PER_CELL."""
    session = rook_session()
    session.drain_deltas()  # clear the initial game-start event
    session.apply_command(Color.WHITE, "WRa1a3")
    assert session.drain_deltas() == [
        Event(SOUND_MOVE),
        MoveStarted(0, "wR", "a1", "a3", 0, 2000),
    ]


def test_an_illegal_move_queues_nothing():
    session = rook_session()
    session.drain_deltas()
    session.apply_command(Color.WHITE, "WRa1b2")  # rejected: illegal
    assert session.drain_deltas() == []


def test_a_quiet_tick_queues_nothing():
    """The saving, in one test: time passing is not news, so it costs no traffic."""
    session = rook_session()
    session.drain_deltas()
    session.tick(50)
    assert session.drain_deltas() == []


def test_arriving_queues_a_settled_then_the_end_of_its_cooldown():
    session = rook_session()
    session.apply_command(Color.WHITE, "WRa1a3")
    session.drain_deltas()

    session.tick(2000)  # the rook arrives
    assert session.drain_deltas() == [Settled(0, "wR", "a3", 2000, COOLDOWN_MS)]

    session.tick(COOLDOWN_MS)  # and is free again
    assert session.drain_deltas() == [CooldownDone(0, 2000 + COOLDOWN_MS)]


def test_capturing_the_king_queues_the_capture_then_the_result():
    session = king_session()
    session.set_rating(Color.WHITE, 1200)
    session.set_rating(Color.BLACK, 1200)
    session.apply_command(Color.WHITE, "WRa1a3")
    session.drain_deltas()  # clear the game-start and move deltas

    session.tick(2000)  # the rook arrives and captures the king

    assert session.drain_deltas() == [
        Event(SOUND_CAPTURE),
        Captured(1, "bK", 2000),
        Event(SOUND_GAME_OVER),
        # Evenly matched, so the win is worth half the K-factor either way.
        GameOver(Color.WHITE, 2000, {Color.WHITE: 1216, Color.BLACK: 1184}),
        Settled(0, "wR", "a3", 2000, COOLDOWN_MS),
    ]


def test_a_game_with_an_unfilled_seat_ends_unrated():
    """A lone room creator can capture the unowned king; that game does not count."""
    session = king_session()
    session.set_rating(Color.WHITE, 1200)  # black never joined
    session.apply_command(Color.WHITE, "WRa1a3")
    session.tick(2000)

    over = [m for m in session.drain_deltas() if isinstance(m, GameOver)]
    assert over == [GameOver(Color.WHITE, 2000, {})]


# --- disconnect and auto-resign (M5) -----------------------------------------

def test_mark_disconnected_shows_a_countdown_in_the_snapshot():
    session = rook_session()
    session.mark_disconnected(Color.BLACK)
    snapshot = session.snapshot()
    assert snapshot.disconnected is Color.BLACK
    assert snapshot.resign_ms == RESIGN_COUNTDOWN_MS


def test_ticking_runs_the_resign_countdown_down():
    session = rook_session()
    session.mark_disconnected(Color.BLACK)
    session.tick(500)
    assert session.snapshot().resign_ms == RESIGN_COUNTDOWN_MS - 500


def test_the_countdown_expiring_resigns_the_missing_player():
    session = rook_session()
    session.drain_deltas()  # clear the initial game-start event
    session.mark_disconnected(Color.BLACK)
    session.tick(RESIGN_COUNTDOWN_MS)
    snapshot = session.snapshot()
    assert snapshot.winner is Color.WHITE   # the missing player's opponent wins
    assert snapshot.phase == "over"
    assert snapshot.disconnected is None    # the countdown is cleared
    assert snapshot.resign_ms == 0
    assert session.drain_deltas() == [
        # The deadline is announced once, not re-sent as a countdown every tick.
        Disconnected(Color.BLACK, RESIGN_COUNTDOWN_MS),
        Event(SOUND_GAME_OVER),
        GameOver(Color.WHITE, 0, {}),
    ]


def test_reconnecting_queues_the_cancellation():
    session = rook_session()
    session.mark_disconnected(Color.BLACK)
    session.drain_deltas()
    session.reconnect()
    assert session.drain_deltas() == [Reconnected()]


def test_no_move_is_accepted_after_a_resign():
    session = rook_session()
    session.resign(Color.BLACK)  # black resigns -> white wins
    assert session.apply_command(Color.WHITE, "WRa1a3") == "game_over"


def test_resigning_an_already_finished_game_is_ignored():
    session = king_session()
    session.apply_command(Color.WHITE, "WRa1a3")
    session.tick(100000)          # white captures the king -> white already won
    session.resign(Color.WHITE)   # would hand the win to black -- must be ignored
    assert session.snapshot().winner is Color.WHITE


def test_a_disconnect_after_the_game_is_over_starts_no_countdown():
    session = king_session()
    session.apply_command(Color.WHITE, "WRa1a3")
    session.tick(100000)          # game already over by capture
    session.mark_disconnected(Color.WHITE)
    assert session.snapshot().disconnected is None


def test_reconnect_cancels_the_countdown():
    session = rook_session()
    session.mark_disconnected(Color.BLACK)
    session.reconnect()
    snapshot = session.snapshot()
    assert snapshot.disconnected is None
    assert snapshot.resign_ms == 0


def test_disconnected_color_and_name_expose_the_missing_seat():
    session = rook_session()
    session.set_name(Color.BLACK, "Dan")
    session.mark_disconnected(Color.BLACK)
    assert session.disconnected_color() is Color.BLACK
    assert session.name_of(Color.BLACK) == "Dan"
    assert session.name_of(Color.WHITE) is None  # nobody logged into that seat


# --- when the game next needs a tick -----------------------------------------

def test_an_idle_game_has_nothing_scheduled():
    assert rook_session().next_event_delay_ms() is None


def test_a_move_in_flight_schedules_its_arrival():
    session = rook_session()
    session.apply_command(Color.WHITE, "WRa1a3")   # two cells
    assert session.next_event_delay_ms() == 2 * MS_PER_CELL

    session.tick(500)
    assert session.next_event_delay_ms() == 2 * MS_PER_CELL - 500  # a delay, not a moment


def test_a_landed_piece_schedules_the_end_of_its_cooldown():
    session = rook_session()
    session.apply_command(Color.WHITE, "WRa1a3")
    session.tick(2 * MS_PER_CELL)
    assert session.next_event_delay_ms() == COOLDOWN_MS


def test_a_missing_player_schedules_their_auto_resign():
    session = rook_session()
    session.assign_color()
    session.mark_disconnected(Color.WHITE)
    assert session.next_event_delay_ms() == RESIGN_COUNTDOWN_MS

    session.tick(RESIGN_COUNTDOWN_MS // 2)
    assert session.next_event_delay_ms() == RESIGN_COUNTDOWN_MS // 2


def test_the_sooner_of_the_board_and_the_countdown_wins():
    session = rook_session()
    session.assign_color()
    session.apply_command(Color.WHITE, "WRa1a3")   # arrives in 2,000 ms
    session.mark_disconnected(Color.BLACK)        # resigns in 20,000 ms
    assert session.next_event_delay_ms() == 2 * MS_PER_CELL


def test_a_finished_game_is_never_woken_again():
    session = king_session()
    session.apply_command(Color.WHITE, "WRa1a3")
    session.tick(2 * MS_PER_CELL)
    assert session.is_over()
    assert session.next_event_delay_ms() is None
