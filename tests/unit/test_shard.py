"""Tests for the shard: what it does with the bus, and how long it sleeps.

``serve`` itself is socket and timer plumbing and is excluded from coverage; this is the
piece of it that has a right and a wrong answer, so it lives at module level and is
tested with a fake hub instead of a running event loop.
"""

from kfchess.bus import subjects
from kfchess.bus.envelope import ClientEvent, ClientEventKind, encode
from kfchess.bus.message_bus import InProcessMessageBus
from kfchess.config import MS_PER_CELL
from kfchess.model.board import Board
from kfchess.model.color import Color
from kfchess.model.piece import Piece
from kfchess.model.piece_type import standard_piece_types
from kfchess.server.shard import Shard, next_sleep_s
from kfchess.server.user_store import UserStore
from kfchess.shared.protocol import Login, Move, Play
from kfchess.shared.protocol import encode as encode_wire


class FakeShard:
    """A shard stand-in that reports whatever the test wants its next event to be."""

    def __init__(self, due_ms):
        self._due_ms = due_ms

    def next_event_delay_ms(self):
        return self._due_ms


def test_an_idle_lobby_waits_out_the_whole_interval():
    assert next_sleep_s(FakeShard(None), 50) == 0.05


def test_a_sooner_event_pulls_the_wake_up_earlier():
    assert next_sleep_s(FakeShard(10), 50) == 0.01


def test_a_later_event_still_waits_no_longer_than_the_ceiling():
    # The resync and the matchmaking timeouts count elapsed time rather than name a
    # moment, so the loop has to come round even when no game needs it.
    assert next_sleep_s(FakeShard(20_000), 50) == 0.05


def test_an_event_that_is_already_due_does_not_sleep_at_all():
    assert next_sleep_s(FakeShard(0), 50) == 0.0


# --- the shard itself ----------------------------------------------------------

def a_shard():
    """A real shard on a fake bus, with the 3x3 rook board the other tests use."""
    reg = standard_piece_types()

    def board():
        return Board.from_grid([
            [None, None, None],
            [None, None, None],
            [Piece(reg.get("R"), Color.WHITE), None, None],
        ])

    bus = InProcessMessageBus()
    return bus, Shard(bus, board, UserStore(":memory:"))


def report(bus, kind, conn_id, text=""):
    """A gateway reporting something, without a gateway being involved."""
    bus.publish(subjects.LOBBY_CMD, encode(ClientEvent(kind, conn_id, text)))


def test_the_shard_reports_when_its_games_next_need_a_tick():
    bus, shard = a_shard()
    assert shard.next_event_delay_ms() is None  # no games at all yet

    for conn_id, name in (("gw1.0", "Efrat"), ("gw1.1", "Dan")):
        report(bus, ClientEventKind.CONNECTED, conn_id)
        report(bus, ClientEventKind.MESSAGE, conn_id, encode_wire(Login(name, "pw")))
        report(bus, ClientEventKind.MESSAGE, conn_id, encode_wire(Play()))
    report(bus, ClientEventKind.MESSAGE, "gw1.0", encode_wire(Move("WRa1a3")))

    assert shard.next_event_delay_ms() == 2 * MS_PER_CELL  # the move in flight


def test_a_message_from_a_connection_the_shard_never_saw_is_dropped():
    """The gateway restarted, or the connect and the message crossed. Not a crash."""
    bus, shard = a_shard()

    report(bus, ClientEventKind.MESSAGE, "gw9.4", encode_wire(Play()))

    assert bus.sent_to(subjects.connection("gw9.4")) == []


def test_a_disconnect_for_a_connection_the_shard_never_saw_is_harmless():
    bus, shard = a_shard()
    report(bus, ClientEventKind.DISCONNECTED, "gw9.4")  # must not raise
    assert shard.next_event_delay_ms() is None
