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


def events(bus, shard_id="sh1"):
    """Every ClientEvent this gateway sent about a connection this shard owns."""
    return [
        decode_client_event(payload)
        for payload in bus.sent_to(subjects.shard_cmd(shard_id))
    ]


def announcements(bus):
    """Every ClientEvent put on the channel for connections nobody owns yet."""
    return [decode_client_event(payload) for payload in bus.sent_to(subjects.LOBBY_CMD)]


def answer(bus, conn_id, text, follow_room=None, claim=None):
    """The shard replying to one connection."""
    bus.publish(
        subjects.connection(conn_id), encode(ToClient(text, follow_room, claim))
    )


def claimed(gateway, bus, shard_id="sh1"):
    """A connection whose gateway has been told which shard owns it."""
    conn_id = gateway.connect(a_socket()[0])
    answer(bus, conn_id, "", claim=shard_id)
    return conn_id


# --- sockets -> the bus -------------------------------------------------------

def test_opening_a_socket_is_announced_to_whichever_shard_is_free():
    gateway, bus = a_gateway()
    conn_id = gateway.connect(a_socket()[0])
    assert announcements(bus) == [ClientEvent(ClientEventKind.CONNECTED, conn_id)]


def test_what_a_client_says_is_forwarded_verbatim_and_unread():
    gateway, bus = a_gateway()
    conn_id = claimed(gateway, bus)

    gateway.receive(conn_id, '{"type": "move", "cmd": "WRa1a3"}')

    assert events(bus)[-1] == ClientEvent(
        ClientEventKind.MESSAGE, conn_id, '{"type": "move", "cmd": "WRa1a3"}'
    )


def test_a_socket_closing_is_reported_to_its_owner():
    gateway, bus = a_gateway()
    conn_id = claimed(gateway, bus)

    gateway.disconnect(conn_id)

    assert events(bus)[-1] == ClientEvent(ClientEventKind.DISCONNECTED, conn_id)


def test_a_socket_closing_before_anyone_claimed_it_is_announced_instead():
    """It may still matter -- somebody has to forget the connect they just registered."""
    gateway, bus = a_gateway()
    conn_id = gateway.connect(a_socket()[0])

    gateway.disconnect(conn_id)

    assert announcements(bus)[-1] == ClientEvent(ClientEventKind.DISCONNECTED, conn_id)


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


# --- who owns a connection ----------------------------------------------------

def test_nothing_is_forwarded_until_a_shard_claims_the_connection():
    """The race the claim exists to lose safely: a login sent before anyone answered."""
    gateway, bus = a_gateway()
    conn_id = gateway.connect(a_socket()[0])

    gateway.receive(conn_id, '{"type": "login"}')

    assert events(bus) == []          # not sent to a shard...
    assert len(announcements(bus)) == 1  # ...and not broadcast to all of them either


def test_what_was_held_is_forwarded_the_moment_the_claim_arrives():
    gateway, bus = a_gateway()
    conn_id = gateway.connect(a_socket()[0])
    gateway.receive(conn_id, '{"type": "login"}')
    gateway.receive(conn_id, '{"type": "play"}')

    answer(bus, conn_id, "", claim="sh1")

    assert [event.text for event in events(bus)] == ['{"type": "login"}', '{"type": "play"}']


def test_a_claim_carrying_no_text_says_nothing_to_the_socket():
    gateway, bus = a_gateway()
    send, received = a_socket()
    conn_id = gateway.connect(send)

    answer(bus, conn_id, "", claim="sh1")

    assert received == []  # the player is not shown an empty message


def test_a_seating_shard_takes_the_connection_over_from_the_one_holding_it():
    """The one thing that moves a connection: being seated in a game somebody else runs."""
    gateway, bus = a_gateway()
    conn_id = claimed(gateway, bus, "sh1")

    answer(bus, conn_id, '{"type": "seated"}', follow_room="7", claim="sh2")
    gateway.receive(conn_id, '{"type": "move", "cmd": "WRa1a3"}')

    assert events(bus, "sh1") == []  # her old shard hears nothing more from her
    assert [event.text for event in events(bus, "sh2")] == [
        '{"type": "move", "cmd": "WRa1a3"}'
    ]


def test_a_connection_that_closed_before_its_claim_forgets_what_it_held():
    gateway, bus = a_gateway()
    conn_id = gateway.connect(a_socket()[0])
    gateway.receive(conn_id, '{"type": "login"}')

    gateway.disconnect(conn_id)
    answer(bus, conn_id, "", claim="sh1")  # the claim arrives after she is gone

    assert [event.kind for event in events(bus, "sh1")] == []
