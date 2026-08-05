"""Tests for ThinClientApp's tested decisions: click handling, winner text, quitting."""

from kfchess.client.app import ThinClientApp
from kfchess.client.controller import ClientController
from kfchess.client.snapshot_view import to_render_inputs
from kfchess.graphics.sound import SoundPlayer
from kfchess.model.color import Color
from kfchess.model.position import Position
from kfchess.movement.rules import standard_movement_rules
from kfchess.rules.rule_engine import RuleEngine
from kfchess.shared.snapshot import CellView, GameSnapshot
from kfchess.shared.codes import Phase

_NAMES = {Color.WHITE: "Efrat", Color.BLACK: "Dan"}
_ESC, _OTHER = 27, ord("x")


class FakeNet:
    def __init__(self, snapshot=None, color=None, events=(), rejection=None):
        self._snapshot = snapshot
        self._color = color
        self._events = list(events)
        self._rejection = rejection
        self.sent = []

    def latest(self):
        return self._snapshot

    @property
    def color(self):
        return self._color

    def queue_command(self, cmd):
        self.sent.append(cmd)

    def next_event(self):
        return self._events.pop(0) if self._events else None

    def take_rejection(self):
        reason, self._rejection = self._rejection, None  # cleared on read, as the real one
        return reason


class SpyPlayer(SoundPlayer):
    def __init__(self):
        self.played = []

    def play(self, sound):
        self.played.append(sound)


def a_snapshot(winner=None, phase=Phase.PLAYING, disconnected=None, resign_ms=0):
    # white rook at (1,0)=a1, black king at (0,1)=b2, on a 2x2 board
    return GameSnapshot(
        rows=2,
        cols=2,
        cells=[[None, CellView("bK", "IDLE")], [CellView("wR", "IDLE"), None]],
        moving=[],
        scores={Color.WHITE: 0, Color.BLACK: 0},
        logs={Color.WHITE: [], Color.BLACK: []},
        names={},
        ratings={},
        phase=phase,
        winner=winner,
        now_ms=0,
        disconnected=disconnected,
        resign_ms=resign_ms,
    )


def an_app(net, sound_player=None, rule_engine=None):
    # renderer/hud_source are unused by the tested methods, so pass None.
    return ThinClientApp(
        net, None, None, ClientController(), _NAMES,
        canvas_size=(100, 100), cell_px=100, board_x_offset=340,
        sound_player=sound_player, rule_engine=rule_engine,
    )


def a_rule_engine():
    """The same read-only legality the server judges with."""
    return RuleEngine(standard_movement_rules())


def select_the_rook(app):
    """Click a1 (row 1, col 0) — the white rook — on the 2x2 test board."""
    app._handle_click(390, 150)


def test_a_click_before_the_first_snapshot_sends_nothing():
    net = FakeNet(snapshot=None, color=Color.WHITE)
    an_app(net)._handle_click(390, 150)
    assert net.sent == []


# --- the move hints ----------------------------------------------------------


def test_nothing_is_tinted_green_while_no_piece_is_selected():
    app = an_app(FakeNet(snapshot=a_snapshot(), color=Color.WHITE),
                 rule_engine=a_rule_engine())
    board, _, _ = to_render_inputs(a_snapshot())
    assert app.legal_hints(board) == ()


def test_a_selected_piece_is_shown_every_square_it_may_reach():
    """The green hints the windowed game has always drawn, now on the networked one.

    Answered against the board rebuilt from the snapshot, so the client shows what the
    server would allow rather than a second opinion about it.
    """
    snapshot = a_snapshot()
    app = an_app(FakeNet(snapshot=snapshot, color=Color.WHITE),
                 rule_engine=a_rule_engine())
    select_the_rook(app)

    board, _, _ = to_render_inputs(snapshot)
    # A rook on a1 of a 2x2 board: up and across, but not diagonally onto the king.
    assert set(app.legal_hints(board)) == {Position(0, 0), Position(1, 1)}


# --- the refused-move outline ------------------------------------------------


def test_a_move_the_server_refuses_outlines_the_square_it_was_aimed_at():
    net = FakeNet(snapshot=a_snapshot(), color=Color.WHITE, rejection="illegal_move")
    app = an_app(net)
    select_the_rook(app)
    app._handle_click(490, 150)  # ...and send it to b1 (row 1, col 1)

    assert app.invalid_cell() == Position(1, 1)


def test_nothing_is_outlined_when_the_server_has_refused_nothing():
    net = FakeNet(snapshot=a_snapshot(), color=Color.WHITE)
    app = an_app(net)
    select_the_rook(app)
    app._handle_click(490, 150)

    assert app.invalid_cell() is None


def test_a_refusal_with_no_move_of_ours_behind_it_outlines_nothing():
    """A rejection can arrive before this client has sent a move to blame it on."""
    net = FakeNet(snapshot=a_snapshot(), color=Color.WHITE, rejection="illegal_move")
    assert an_app(net).invalid_cell() is None


def test_selecting_then_clicking_a_target_queues_the_command():
    net = FakeNet(snapshot=a_snapshot(), color=Color.WHITE)
    app = an_app(net)
    app._handle_click(390, 150)  # canvas -> cell (1,0): select the rook at a1
    app._handle_click(390, 50)   # canvas -> cell (0,0): move to a2
    assert net.sent == ["WRa1a2"]


def test_a_spectator_click_sends_nothing():
    net = FakeNet(snapshot=a_snapshot(), color=None)  # no colour assigned
    app = an_app(net)
    app._handle_click(390, 150)
    app._handle_click(390, 50)
    assert net.sent == []


def test_winner_text_uses_the_player_name_or_falls_back():
    app = an_app(FakeNet())
    assert app._winner_text(a_snapshot(winner=Color.WHITE)) == "Efrat wins!"
    assert app._winner_text(a_snapshot(winner=None)) == "Game Over"


def test_countdown_text_rounds_the_remaining_seconds_up():
    app = an_app(FakeNet())
    snapshot = a_snapshot(disconnected=Color.BLACK, resign_ms=11200)
    assert app._countdown_text(snapshot) == "Opponent disconnected -- resigning in 12s"


def test_no_countdown_text_when_nobody_has_disconnected():
    assert an_app(FakeNet())._countdown_text(a_snapshot()) is None


def test_no_countdown_text_once_the_game_is_over():
    app = an_app(FakeNet())
    snapshot = a_snapshot(phase=Phase.OVER, disconnected=Color.BLACK, resign_ms=5000)
    assert app._countdown_text(snapshot) is None


def test_quits_on_escape_or_a_closed_window():
    app = an_app(FakeNet())
    assert app._should_quit(_ESC, False) is True
    assert app._should_quit(_OTHER, True) is True
    assert app._should_quit(_OTHER, False) is False


def test_default_sound_player_is_silent():
    app = an_app(FakeNet(events=["move", "capture"]))
    app._play_pending_sounds()  # SoundPlayer() default: must not raise, no assertion needed


def test_pending_sound_events_are_played_in_order():
    spy = SpyPlayer()
    app = an_app(FakeNet(events=["move", "capture", "game_over"]), sound_player=spy)
    app._play_pending_sounds()
    assert spy.played == ["move", "capture", "game_over"]


def test_no_pending_events_plays_nothing():
    spy = SpyPlayer()
    an_app(FakeNet(events=[]), sound_player=spy)._play_pending_sounds()
    assert spy.played == []
