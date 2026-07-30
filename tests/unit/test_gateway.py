"""Tests for the Gateway: text in from a socket, text out to a subject, and back.

Everything runs on InProcessMessageBus, so a whole gateway is driven by calling methods and
read by looking at what reached the bus. No sockets, no event loop.
"""

from kfchess.bus import subjects
from kfchess.bus.envelope import (
    ClientEvent,
    ClientEventKind,
    ToClient,
    decode_client_event,
    encode,
)
from kfchess.bus.message_bus import InProcessMessageBus
from kfchess.gateway.app import Gateway


def a_gateway(gateway_id="gw1"):
    bus = InProcessMessageBus()
    return Gateway(bus, gateway_id), bus


def a_socket():
    received = []
    return received.append, received


def events(bus):
    """Every ClientEvent this gateway put on the pre-room channel."""
    return [decode_client_event(payload) for payload in bus.sent_to(subjects.LOBBY_CMD)]


def answer(bus, conn_id, text, follow_room=None):
    """The shard replying to one connection."""
    bus.publish(subjects.connection(conn_id), encode(ToClient(text, follow_room)))


# --- sockets -> the bus -------------------------------------------------------

def test_opening_a_socket_is_reported_to_the_shard():
    gateway, bus = a_gateway()
    conn_id = gateway.connect(a_socket()[0])
    assert events(bus) == [ClientEvent(ClientEventKind.CONNECTED, conn_id)]


def test_what_a_client_says_is_forwarded_verbatim_and_unread():
    gateway, bus = a_gateway()
    conn_id = gateway.connect(a_socket()[0])

    gateway.receive(conn_id, '{"type": "move", "cmd": "WRa1a3"}')

    assert events(bus)[-1] == ClientEvent(
        ClientEventKind.MESSAGE, conn_id, '{"type": "move", "cmd": "WRa1a3"}'
    )


def test_a_socket_closing_is_reported_too():
    gateway, bus = a_gateway()
    conn_id = gateway.connect(a_socket()[0])

    gateway.disconnect(conn_id)

    assert events(bus)[-1] == ClientEvent(ClientEventKind.DISCONNECTED, conn_id)


def test_the_gateway_counts_its_sockets():
    gateway, _ = a_gateway()
    first = gateway.connect(a_socket()[0])
    gateway.connect(a_socket()[0])
    assert gateway.connections == 2

    gateway.disconnect(first)
    assert gateway.connections == 1


# --- the bus -> sockets -------------------------------------------------------

def test_a_reply_reaches_the_one_connection_it_was_addressed_to():
    gateway, bus = a_gateway()
    mine, mine_received = a_socket()
    theirs, theirs_received = a_socket()
    conn_id = gateway.connect(mine)
    gateway.connect(theirs)

    answer(bus, conn_id, '{"type": "welcome"}')

    assert mine_received == ['{"type": "welcome"}']
    assert theirs_received == []


def test_a_reply_for_a_socket_that_already_closed_is_dropped():
    gateway, bus = a_gateway()
    send, received = a_socket()
    conn_id = gateway.connect(send)
    gateway.disconnect(conn_id)

    answer(bus, conn_id, "too late")  # crossed with the close

    assert received == []


def test_another_gateways_mail_is_never_delivered_here():
    gateway, bus = a_gateway("gw1")
    send, received = a_socket()
    gateway.connect(send)

    bus.publish(subjects.connection("gw2.0"), encode(ToClient("not ours")))

    assert received == []


# --- rooms, players and spectators alike ---------------------------------------

def test_being_given_a_place_starts_following_that_rooms_broadcasts():
    gateway, bus = a_gateway()
    send, received = a_socket()
    conn_id = gateway.connect(send)

    answer(bus, conn_id, '{"type": "seated"}', follow_room="4")
    bus.publish(subjects.room_delta("4"), '{"type": "move_started"}')

    assert received == ['{"type": "seated"}', '{"type": "move_started"}']


def test_a_broadcast_reaches_players_and_spectators_the_same_way():
    """The gateway cannot tell them apart, and nothing here needs to."""
    gateway, bus = a_gateway()
    sockets = [a_socket() for _ in range(4)]  # white, black, and two watchers
    for send, _ in sockets:
        answer(bus, gateway.connect(send), '{"type": "seated"}', follow_room="4")

    bus.publish(subjects.room_state("4"), '{"type": "state"}')

    for _, received in sockets:
        assert received[-1] == '{"type": "state"}'


def test_a_rooms_traffic_crosses_the_bus_once_however_many_are_watching():
    """The property the room subjects exist for: one delivery here, four sends there."""
    gateway, bus = a_gateway()
    deliveries = []
    for send, _ in [a_socket() for _ in range(4)]:
        answer(bus, gateway.connect(send), "seated", follow_room="4")
    bus.subscribe(subjects.room_inbox("4"), lambda subject, payload: deliveries.append(payload))

    bus.publish(subjects.room_delta("4"), "one delta")

    assert deliveries == ["one delta"]  # not four


def test_a_spectator_leaving_does_not_stop_the_game_being_followed():
    gateway, bus = a_gateway()
    player, player_received = a_socket()
    watcher, _ = a_socket()
    player_id = gateway.connect(player)
    watcher_id = gateway.connect(watcher)
    answer(bus, player_id, "seated", follow_room="4")
    answer(bus, watcher_id, "seated", follow_room="4")

    gateway.disconnect(watcher_id)
    bus.publish(subjects.room_delta("4"), "still playing")

    assert player_received[-1] == "still playing"


def test_the_last_one_out_of_a_room_stops_the_subscription():
    gateway, bus = a_gateway()
    send, received = a_socket()
    conn_id = gateway.connect(send)
    answer(bus, conn_id, "seated", follow_room="4")

    gateway.disconnect(conn_id)
    bus.publish(subjects.room_delta("4"), "nobody here")

    assert received == ["seated"]  # the room's traffic is no longer being pulled


def test_a_second_room_is_followed_independently():
    gateway, bus = a_gateway()
    here, here_received = a_socket()
    there, there_received = a_socket()
    answer(bus, gateway.connect(here), "seated", follow_room="4")
    answer(bus, gateway.connect(there), "seated", follow_room="9")

    bus.publish(subjects.room_delta("4"), "game four")

    assert here_received[-1] == "game four"
    assert there_received == ["seated"]
