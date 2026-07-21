"""Tests for ThinClientApp's tested decisions: click handling, winner text, quitting."""

from kfchess.client.app import ThinClientApp
from kfchess.client.controller import ClientController
from kfchess.graphics.sound import SoundPlayer
from kfchess.model.color import Color
from kfchess.snapshot import CellView, GameSnapshot

_NAMES = {Color.WHITE: "Efrat", Color.BLACK: "Dan"}
_ESC, _OTHER = 27, ord("x")


class FakeNet:
    def __init__(self, snapshot=None, color=None, events=()):
        self._snapshot = snapshot
        self._color = color
        self._events = list(events)
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


class SpyPlayer(SoundPlayer):
    def __init__(self):
        self.played = []

    def play(self, sound):
        self.played.append(sound)


def a_snapshot(winner=None):
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
        phase="playing",
        winner=winner,
        now_ms=0,
    )


def an_app(net, sound_player=None):
    # renderer/hud_source are unused by the tested methods, so pass None.
    return ThinClientApp(
        net, None, None, ClientController(), _NAMES,
        canvas_size=(100, 100), cell_px=100, board_x_offset=340,
        sound_player=sound_player,
    )


def test_a_click_before_the_first_snapshot_sends_nothing():
    net = FakeNet(snapshot=None, color=Color.WHITE)
    an_app(net)._handle_click(390, 150)
    assert net.sent == []


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
