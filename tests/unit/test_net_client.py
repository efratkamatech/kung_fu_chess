"""Tests for NetClient's synchronous bridge logic (no sockets, no threads)."""

from kfchess.client.net_client import NetClient
from kfchess.model.color import Color
from kfchess.protocol import Event, Move, Rejected, Seated, State, Welcome, encode
from kfchess.snapshot import CellView, GameSnapshot


def a_snapshot(now_ms=7):
    return GameSnapshot(
        rows=1,
        cols=1,
        cells=[[CellView("wK", "IDLE")]],
        moving=[],
        scores={Color.WHITE: 0, Color.BLACK: 0},
        logs={Color.WHITE: [], Color.BLACK: []},
        names={},
        ratings={},
        phase="playing",
        winner=None,
        now_ms=now_ms,
    )


def test_starts_empty():
    client = NetClient()
    assert client.latest() is None
    assert client.color is None
    assert client.rating is None
    assert client.take_rejection() is None
    assert client.next_event() is None


def test_a_state_message_becomes_the_latest_snapshot():
    client = NetClient()
    snapshot = a_snapshot(now_ms=42)
    client.handle(encode(State(snapshot)))
    assert client.latest() == snapshot


def test_a_later_state_replaces_the_earlier_one():
    client = NetClient()
    client.handle(encode(State(a_snapshot(now_ms=1))))
    client.handle(encode(State(a_snapshot(now_ms=2))))
    assert client.latest().now_ms == 2


def test_a_welcome_sets_the_colour_and_rating():
    client = NetClient()
    client.handle(encode(Welcome(Color.BLACK, 1234)))
    assert client.color is Color.BLACK
    assert client.rating == 1234


def test_a_spectator_welcome_has_no_colour_but_still_a_rating():
    client = NetClient()
    client.handle(encode(Welcome(None, 1200)))
    assert client.color is None
    assert client.rating == 1200


def test_a_seated_message_sets_the_colour_matchmaking_assigned():
    client = NetClient()
    client.handle(encode(Welcome(None, 1200)))  # logged in, no seat yet
    client.handle(encode(Seated(Color.BLACK)))  # then matched into a game
    assert client.color is Color.BLACK


def test_a_move_rejection_after_login_is_reported_once_then_cleared():
    client = NetClient()
    client.handle(encode(Welcome(Color.WHITE, 1200)))  # logged in first
    client.handle(encode(Rejected("illegal_move")))
    assert client.take_rejection() == "illegal_move"
    assert client.take_rejection() is None  # cleared on read


def test_garbage_messages_are_ignored():
    client = NetClient()
    client.handle("not json")
    client.handle(encode(State(a_snapshot())))  # a real message still works after garbage
    assert client.latest() is not None


def test_a_welcome_reports_login_success():
    client = NetClient()
    client.handle(encode(Welcome(Color.WHITE, 1200)))
    assert client.wait_for_login() is None  # accepted


def test_a_rejection_before_login_is_a_login_failure():
    client = NetClient()
    client.handle(encode(Rejected("bad_password")))
    assert client.wait_for_login() == "bad_password"  # not a move rejection
    assert client.take_rejection() is None            # so the move-rejection slot stays clear


def test_an_unexpected_message_type_is_ignored():
    client = NetClient()
    client.handle(encode(Move("WQe2e5")))  # the server never sends a Move to a client
    assert client.latest() is None
    assert client.color is None
    assert client.take_rejection() is None


def test_queued_commands_come_back_out_in_order():
    client = NetClient()
    client.queue_command("WQe2e5")
    client.queue_command("BPe7e5")
    assert client.next_command() == "WQe2e5"
    assert client.next_command() == "BPe7e5"


def test_a_queued_login_is_available_to_the_network_thread():
    client = NetClient()
    client.login("Efrat", "secret")
    assert client.next_login() == ("Efrat", "secret")


def test_an_event_message_is_queued_for_next_event():
    client = NetClient()
    client.handle(encode(Event("capture")))
    assert client.next_event() == "capture"
    assert client.next_event() is None  # consumed, not just "latest"


def test_multiple_events_come_back_out_in_order():
    client = NetClient()
    client.handle(encode(Event("move")))
    client.handle(encode(Event("game_over")))
    assert client.next_event() == "move"
    assert client.next_event() == "game_over"
    assert client.next_event() is None
