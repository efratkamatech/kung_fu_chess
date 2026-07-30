"""Tests for ClientGameState: deltas in, a snapshot the renderer can draw out.

The last test is the one that matters most — it plays a scripted game on a real
GameSession and asserts that what the client rebuilds from the deltas is *equal* to what
the server holds, tick by tick. Any delta the protocol forgets to send shows up there as
a difference, which is the whole risk of moving off full snapshots.
"""

import pytest

from kfchess.client.game_state import ClientGameState, ServerClock, monotonic_ms
from kfchess.config import COOLDOWN_MS, MS_PER_CELL
from kfchess.model.board import Board
from kfchess.model.color import Color
from kfchess.model.piece import Piece
from kfchess.model.piece_type import standard_piece_types
from kfchess.server.session import GameSession
from kfchess.shared import protocol
from kfchess.shared.codes import Phase
from kfchess.shared.snapshot import CellView, GameSnapshot, MovingView


def frozen(now_ms=0):
    """A ServerClock whose local time never advances, so tests read exact numbers."""
    return ServerClock(lambda: now_ms)


def a_snapshot(**overrides):
    """A 3x3 board with a white rook on a1 (row 2, col 0), unless overridden."""
    cells = [[None] * 3 for _ in range(3)]
    cells[2][0] = CellView("wR", "IDLE", 0.0, 7)
    fields = dict(
        rows=3,
        cols=3,
        cells=cells,
        moving=[],
        scores={Color.WHITE: 0, Color.BLACK: 0},
        logs={Color.WHITE: [], Color.BLACK: []},
        names={Color.WHITE: "Efrat"},
        ratings={Color.WHITE: 1200},
        phase=Phase.PLAYING,
        winner=None,
        now_ms=1_000,
    )
    fields.update(overrides)
    return GameSnapshot(**fields)


def a_state(clock=None):
    """A state seeded with :func:`a_snapshot`, ready to take deltas."""
    state = ClientGameState(clock if clock is not None else frozen())
    state.reset(a_snapshot())
    return state


# --- before anything has arrived --------------------------------------------


def test_there_is_nothing_to_draw_before_the_first_snapshot():
    state = ClientGameState(frozen())
    assert state.snapshot(0) is None
    assert state.current() is None


def test_a_delta_before_the_first_snapshot_is_dropped():
    state = ClientGameState(frozen())
    state.apply(protocol.CooldownDone(7, 5))
    assert state.snapshot(0) is None  # still nothing; it had nowhere to land


def test_a_message_that_is_not_about_the_game_is_ignored():
    state = a_state()
    state.apply(protocol.Event("capture"))  # a sound, not a change to the board
    assert state.snapshot(1_000) == a_snapshot()


# --- the full snapshot ------------------------------------------------------


def test_a_full_snapshot_is_reproduced_exactly():
    assert a_state().snapshot(1_000) == a_snapshot()


def test_the_snapshot_is_read_at_the_clock_the_server_last_reported():
    state = a_state()
    assert state.current().now_ms == 1_000


def test_local_time_carries_the_clock_forward_between_messages():
    local = [0]
    state = ClientGameState(ServerClock(lambda: local[0]))
    state.reset(a_snapshot())  # the server said 1,000 as of local time 0
    local[0] = 250             # a quarter-second of frames later, with no message
    assert state.current().now_ms == 1_250


def test_a_cooldown_fraction_survives_the_round_trip():
    cells = [[None] * 3 for _ in range(3)]
    cells[2][0] = CellView("wR", "COOLDOWN", 0.5, 7)
    state = ClientGameState(frozen())
    state.reset(a_snapshot(cells=cells))

    assert state.snapshot(1_000).cells[2][0] == CellView("wR", "COOLDOWN", 0.5, 7)
    # ...and it keeps draining on its own, without another message.
    assert state.snapshot(1_000 + COOLDOWN_MS // 4).cells[2][0].cooldown == 0.25
    assert state.snapshot(1_000 + COOLDOWN_MS).cells[2][0].state == "IDLE"


# --- deltas ------------------------------------------------------------------


def test_a_move_takes_the_piece_off_its_square_and_puts_it_in_flight():
    state = a_state()
    state.apply(protocol.MoveStarted(7, "wR", "a1", "a3", 1_000, 3_000))

    snapshot = state.snapshot(1_000)
    assert snapshot.cells[2][0] is None          # no longer settled anywhere
    assert snapshot.moving == [MovingView("wR", 2.0, 0.0, 7)]


def test_a_flying_piece_is_interpolated_between_its_endpoints():
    state = a_state()
    state.apply(protocol.MoveStarted(7, "wR", "a1", "a3", 1_000, 3_000))

    assert state.snapshot(2_000).moving == [MovingView("wR", 1.0, 0.0, 7)]
    # Clamped: it does not run past its destination if the landing is late.
    assert state.snapshot(9_000).moving == [MovingView("wR", 0.0, 0.0, 7)]


def test_a_move_is_logged_to_the_movers_side():
    state = a_state()
    state.apply(protocol.MoveStarted(7, "wR", "a1", "a3", 1_000, 3_000))

    assert state.snapshot(1_000).logs[Color.WHITE] == ["wR a1 -> a3"]
    assert state.snapshot(1_000).logs[Color.BLACK] == []


def test_the_first_move_dismisses_the_start_banner():
    state = ClientGameState(frozen())
    state.reset(a_snapshot(phase=Phase.START))
    assert state.snapshot(1_000).phase is Phase.START

    state.apply(protocol.MoveStarted(7, "wR", "a1", "a3", 1_000, 3_000))
    assert state.snapshot(1_000).phase is Phase.PLAYING


def test_settling_puts_the_piece_back_on_the_board_on_cooldown():
    state = a_state()
    state.apply(protocol.MoveStarted(7, "wR", "a1", "a3", 1_000, 3_000))
    state.apply(protocol.Settled(7, "wR", "a3", 3_000, COOLDOWN_MS))

    snapshot = state.snapshot(3_000)
    assert snapshot.moving == []
    assert snapshot.cells[0][0] == CellView("wR", "COOLDOWN", 1.0, 7)


def test_a_pawn_settles_as_whatever_it_promoted_to():
    state = a_state()
    state.apply(protocol.Settled(7, "wQ", "a3", 3_000, COOLDOWN_MS))
    assert state.snapshot(3_000).cells[0][0].token == "wQ"


def test_cooldown_done_frees_the_piece_at_the_moment_it_really_ended():
    state = a_state()
    state.apply(protocol.Settled(7, "wR", "a3", 3_000, COOLDOWN_MS))
    state.apply(protocol.CooldownDone(7, 3_500))  # ended early, and says when

    assert state.snapshot(3_500).cells[0][0] == CellView("wR", "IDLE", 0.0, 7)


def test_cooldown_done_for_a_piece_that_is_gone_is_dropped():
    state = a_state()
    state.apply(protocol.Captured(7, "wR", 2_000))
    state.apply(protocol.CooldownDone(7, 2_500))  # captured while cooling down

    assert state.snapshot(2_500).cells[2][0] is None


def test_a_settled_piece_that_is_captured_leaves_the_board_and_scores():
    state = a_state()
    state.apply(protocol.Captured(7, "wR", 2_000))

    snapshot = state.snapshot(2_000)
    assert snapshot.cells[2][0] is None
    rook_value = standard_piece_types().get("R").cost
    assert snapshot.scores[Color.BLACK] == rook_value  # credited to the captor's side
    assert snapshot.logs[Color.BLACK] == ["x wR"]


def test_a_piece_captured_in_flight_leaves_the_board_too():
    state = a_state()
    state.apply(protocol.MoveStarted(7, "wR", "a1", "a3", 1_000, 3_000))
    state.apply(protocol.Captured(7, "wR", 2_000))

    assert state.snapshot(2_000).moving == []


def test_game_over_carries_the_winner_the_phase_and_the_new_ratings():
    state = a_state()
    state.apply(protocol.GameOver(Color.WHITE, 5_000, {Color.WHITE: 1216}))

    snapshot = state.snapshot(5_000)
    assert snapshot.winner is Color.WHITE
    assert snapshot.phase is Phase.OVER
    assert snapshot.ratings[Color.WHITE] == 1216


def test_a_disconnect_deadline_becomes_a_countdown_that_drains():
    state = a_state()
    state.apply(protocol.Disconnected(Color.BLACK, 31_000))

    assert state.snapshot(1_000).resign_ms == 30_000
    assert state.snapshot(21_000).resign_ms == 10_000  # without another message
    assert state.snapshot(99_000).resign_ms == 0       # and never goes negative
    assert state.snapshot(1_000).disconnected is Color.BLACK


def test_a_reconnect_cancels_the_countdown():
    state = a_state()
    state.apply(protocol.Disconnected(Color.BLACK, 31_000))
    state.apply(protocol.Reconnected())

    snapshot = state.snapshot(2_000)
    assert snapshot.disconnected is None
    assert snapshot.resign_ms == 0


# --- resync and reconnect ----------------------------------------------------


def test_a_resync_leaves_a_move_this_client_already_knows_about_running():
    state = a_state()
    state.apply(protocol.MoveStarted(7, "wR", "a1", "a3", 1_000, 3_000))
    # The resync reports where the piece is; its destination and timing are not in
    # there, but this client started the flight and still has them.
    state.reset(a_snapshot(cells=[[None] * 3 for _ in range(3)],
                           moving=[MovingView("wR", 1.5, 0.0, 7)],
                           now_ms=1_500))

    assert state.snapshot(2_000).moving == [MovingView("wR", 1.0, 0.0, 7)]


def test_a_flight_met_for_the_first_time_is_held_until_it_lands():
    state = ClientGameState(frozen())  # a spectator joining mid-air
    state.reset(a_snapshot(cells=[[None] * 3 for _ in range(3)],
                           moving=[MovingView("wR", 1.5, 0.0, 7)],
                           now_ms=1_500))

    assert state.snapshot(2_500).moving == [MovingView("wR", 1.5, 0.0, 7)]
    state.apply(protocol.Settled(7, "wR", "a3", 3_000, COOLDOWN_MS))
    assert state.snapshot(3_000).cells[0][0].token == "wR"


def test_a_snapshot_replaces_scores_and_logs_a_returning_client_never_saw():
    state = a_state()
    state.reset(a_snapshot(scores={Color.WHITE: 3, Color.BLACK: 0},
                           logs={Color.WHITE: ["wR a1 -> a3"], Color.BLACK: []}))

    snapshot = state.snapshot(1_000)
    assert snapshot.scores[Color.WHITE] == 3
    assert snapshot.logs[Color.WHITE] == ["wR a1 -> a3"]


# --- the clock ---------------------------------------------------------------


def test_the_clock_ignores_a_stamp_older_than_where_it_already_is():
    clock = frozen()
    clock.sync(5_000)
    clock.sync(4_000)  # a CooldownDone carries when a cooldown *ended*, not "now"
    assert clock.now_ms == 5_000


def test_the_default_clock_reads_real_local_time():
    assert monotonic_ms() > 0
    assert ClientGameState().current() is None  # builds its own clock, draws nothing yet


# --- the acceptance test: the client's picture equals the server's -----------


def scripted_session():
    """A 3x3 board: a white rook on a1 with a black pawn two squares up its file."""
    types = standard_piece_types()
    grid = [
        [Piece(types.get("P"), Color.BLACK), None, None],
        [None, None, None],
        [Piece(types.get("R"), Color.WHITE), None, None],
    ]
    session = GameSession(Board.from_grid(grid))
    session.set_name(Color.WHITE, "Efrat")
    session.set_name(Color.BLACK, "Dan")
    session.set_rating(Color.WHITE, 1200)
    session.set_rating(Color.BLACK, 1200)
    return session


@pytest.mark.parametrize("command", ["WRa1a2", "WRa1a3"])
def test_the_client_rebuilds_exactly_what_the_server_holds(command):
    """A quiet move and a capture, tick by tick, with no snapshot after the first."""
    session = scripted_session()
    state = ClientGameState(frozen())
    state.reset(session.snapshot())  # seating sends one, and then only deltas
    session.drain_deltas()           # the queued game-start sound

    assert session.apply_command(Color.WHITE, command) is None
    for _ in range(2 * MS_PER_CELL // 50 + COOLDOWN_MS // 50 + 2):
        session.tick(50)
        for message in session.drain_deltas():
            state.apply(message)
        expected = session.snapshot()
        assert state.snapshot(expected.now_ms) == expected
