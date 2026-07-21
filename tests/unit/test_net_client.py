"""Tests for NetClient's synchronous bridge logic (no sockets, no threads)."""

from kfchess.client.net_client import NetClient
from kfchess.model.color import Color
from kfchess.protocol import Assigned, Event, Move, Rejected, State, encode
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
        phase="playing",
        winner=None,
        now_ms=now_ms,
    )


def test_starts_empty():
    client = NetClient()
    assert client.latest() is None
    assert client.color is None
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


def test_an_assigned_message_sets_the_colour():
    client = NetClient()
    client.handle(encode(Assigned(Color.BLACK)))
    assert client.color is Color.BLACK


def test_a_rejection_is_reported_once_then_cleared():
    client = NetClient()
    client.handle(encode(Rejected("illegal_move")))
    assert client.take_rejection() == "illegal_move"
    assert client.take_rejection() is None  # cleared on read


def test_garbage_messages_are_ignored():
    client = NetClient()
    client.handle("not json")
    client.handle(encode(Rejected("x")))  # a real message, keeps working after garbage
    assert client.latest() is None
    assert client.take_rejection() == "x"


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
