"""Tests for the shard: what it does with the bus, and how long it sleeps.

``serve`` itself is socket and timer plumbing and is excluded from coverage; this is the
piece of it that has a right and a wrong answer, so it lives at module level and is
tested with a fake hub instead of a running event loop.
"""

from kfchess.auth.service import AuthService
from kfchess.bus import subjects
from kfchess.bus.envelope import ClientEvent, ClientEventKind, encode
from kfchess.bus.message_bus import InProcessMessageBus
from kfchess.config import MS_PER_CELL, SHARD_HEARTBEAT_MS
from kfchess.model.board import Board
from kfchess.model.color import Color
from kfchess.model.piece import Piece
from kfchess.model.piece_type import standard_piece_types
from kfchess.server.shard import Shard, next_sleep_s
from kfchess.server.user_store import UserStore
from kfchess.services.shared import SharedState
from kfchess.services.store import InMemoryKeyValueStore
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
    users = UserStore(":memory:")
    AuthService(bus, users)
    return bus, Shard(bus, board, users)


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


# --- staying in the pool -------------------------------------------------------

def a_pooled_shard():
    """A shard whose pool a test can read, and the store it reports into."""
    reg = standard_piece_types()

    def board():
        return Board.from_grid([
            [None, None, None],
            [None, None, None],
            [Piece(reg.get("R"), Color.WHITE), None, None],
        ])

    store = InMemoryKeyValueStore()
    shared = SharedState.on(store, "sh1")
    bus = InProcessMessageBus()
    users = UserStore(":memory:")
    AuthService(bus, users)
    return bus, Shard(bus, board, users, shared), shared, store


def test_a_shard_is_in_the_pool_before_its_first_tick():
    """A shard that just started must be allocatable at once, not in five seconds."""
    _, _, shared, _ = a_pooled_shard()

    assert shared.allocator.allocate() == "sh1"


def test_the_heartbeat_reports_how_many_games_are_running():
    bus, shard, _, store = a_pooled_shard()
    for number, name in enumerate(("Efrat", "Dan")):  # two players -> one game
        report(bus, ClientEventKind.CONNECTED, f"gw1.{number}")
        report(bus, ClientEventKind.MESSAGE, f"gw1.{number}", encode_wire(Login(name, "pw")))
        report(bus, ClientEventKind.MESSAGE, f"gw1.{number}", encode_wire(Play()))

    shard.tick(SHARD_HEARTBEAT_MS)

    assert store.get("shard:sh1:alive") == "1"


def test_a_shard_does_not_report_on_every_tick():
    """Twenty writes a second per shard, for a number that changes once a minute."""
    _, shard, shared, _ = a_pooled_shard()
    writes = []
    shared.allocator.announce = lambda *args: writes.append(args)

    for _ in range(10):
        shard.tick(SHARD_HEARTBEAT_MS // 10 - 1)

    assert writes == []


def test_releasing_a_connection_this_shard_never_held_is_harmless():
    """A release can arrive twice, or late. It must not be the thing that takes a shard down."""
    bus, shard = a_shard()

    report(bus, ClientEventKind.RELEASED, "gw9.4")

    assert shard.clients == 0


def test_an_auth_answer_for_a_connection_that_has_gone_is_dropped():
    """The other side of the same race, one layer out."""
    from kfchess.bus.envelope import AuthResult
    from kfchess.bus.envelope import encode as encode_envelope

    bus, shard = a_shard()
    report(bus, ClientEventKind.CONNECTED, "gw1.0")
    report(bus, ClientEventKind.DISCONNECTED, "gw1.0")

    from kfchess.config import SHARD_ID  # this shard answers to its own name

    bus.publish(
        subjects.shard_auth(SHARD_ID),
        encode_envelope(AuthResult("gw1.0", "Efrat", 1200)),
    )

    assert shard.clients == 0


def test_a_shard_publishes_how_many_connections_it_believes_it_holds():
    """Summed across shards this equals the gateways' count; drift is a lost disconnect."""
    from kfchess.obs.measures import CLIENTS

    bus, shard, _, _ = a_pooled_shard()
    report(bus, ClientEventKind.CONNECTED, "gw1.0")
    report(bus, ClientEventKind.CONNECTED, "gw1.1")

    shard.tick(1)

    assert CLIENTS.value == 2


# --- draining, so a deploy costs nobody a game ---------------------------------

def seat_a_game(bus):
    """Two players, logged in and matched: one game, running."""
    for number, name in enumerate(("Efrat", "Dan")):
        report(bus, ClientEventKind.CONNECTED, f"gw1.{number}")
        report(bus, ClientEventKind.MESSAGE, f"gw1.{number}", encode_wire(Login(name, "pw")))
        report(bus, ClientEventKind.MESSAGE, f"gw1.{number}", encode_wire(Play()))


def test_a_draining_shard_leaves_the_pool_at_once():
    """Not in fifteen seconds, when the TTL runs out -- now, before the next allocation."""
    _, shard, shared, _ = a_pooled_shard()

    shard.drain()

    assert shared.allocator.allocate() is None


def test_the_heartbeat_does_not_put_a_draining_shard_back_in_the_pool():
    """The announcement is the one thing that would undo a drain, five seconds later."""
    _, shard, shared, _ = a_pooled_shard()
    shard.drain()

    shard.tick(SHARD_HEARTBEAT_MS)

    assert shared.allocator.allocate() is None


def test_a_draining_shard_stops_claiming_unowned_connections():
    """A socket announced to every shard at once must go to one that is staying."""
    bus, shard, _, _ = a_pooled_shard()

    shard.drain()
    report(bus, ClientEventKind.CONNECTED, "gw1.7")

    assert shard.clients == 0


def test_a_draining_shard_still_serves_the_players_it_already_has():
    """The whole point: a game in progress is finished, not cut off.

    Her move arrives on this shard's own subject rather than the shared one, which is
    where a seated player's messages have come from since she was claimed — and is
    exactly why unsubscribing from the shared subject costs her nothing.
    """
    bus, shard, _, _ = a_pooled_shard()
    seat_a_game(bus)

    shard.drain()
    bus.publish(
        subjects.shard_cmd("sh1"),
        encode(ClientEvent(ClientEventKind.MESSAGE, "gw1.0", encode_wire(Move("WRa1a3")))),
    )

    assert shard.next_event_delay_ms() == 2 * MS_PER_CELL  # the move is in flight


def test_a_shard_is_not_finished_while_a_game_is_running():
    bus, shard, _, _ = a_pooled_shard()
    seat_a_game(bus)

    shard.drain()

    assert shard.finished is False


def test_a_drained_shard_with_no_games_left_is_finished():
    _, shard, _, _ = a_pooled_shard()

    shard.drain()

    assert shard.finished is True


def test_a_shard_that_was_never_asked_to_stop_is_never_finished():
    """An idle shard has no games either, and must not mistake that for permission to go."""
    _, shard, _, _ = a_pooled_shard()

    assert shard.finished is False


def test_draining_twice_is_draining_once():
    """A second SIGTERM must not unsubscribe a subscription that has already gone."""
    _, shard, shared, _ = a_pooled_shard()
    shard.drain()

    shard.drain()  # must not raise

    assert shared.allocator.allocate() is None
