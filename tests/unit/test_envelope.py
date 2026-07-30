"""Tests for the gateway/shard envelope: it round-trips, and it carries the routing."""

from kfchess.bus.envelope import (
    ClientEvent,
    ClientEventKind,
    ToClient,
    decode_client_event,
    decode_to_client,
    encode,
)


def test_a_client_message_round_trips_with_its_connection():
    event = ClientEvent(ClientEventKind.MESSAGE, "gw1.7", '{"type": "play"}')
    assert decode_client_event(encode(event)) == event


def test_a_connect_and_a_disconnect_carry_no_text():
    for kind in (ClientEventKind.CONNECTED, ClientEventKind.DISCONNECTED):
        event = ClientEvent(kind, "gw1.7")
        assert decode_client_event(encode(event)) == event
        assert event.text == ""


def test_the_kind_travels_as_its_plain_string():
    assert '"kind": "message"' in encode(ClientEvent(ClientEventKind.MESSAGE, "gw1.7"))


def test_a_reply_round_trips():
    assert decode_to_client(encode(ToClient("some wire text"))) == ToClient("some wire text")


def test_a_seat_tells_the_gateway_which_room_to_follow():
    """The one thing the gateway is told about the game -- and it is told, not shown."""
    reply = ToClient('{"type": "seated"}', follow_room="4")

    decoded = decode_to_client(encode(reply))

    assert decoded.follow_room == "4"
    assert decoded.text == '{"type": "seated"}'  # opaque; the gateway never reads it


def test_an_ordinary_reply_joins_nothing():
    assert decode_to_client(encode(ToClient("a refusal"))).follow_room is None
