"""Tests for ConnectionRouter: connection ids, and one room subscription per room.

The counting rule is the point of the file. A room is followed once by a gateway however
many of its sockets are in it, and stops being followed the moment the last one leaves —
so most of these tests are about a room with more than two people in it, which is to say
about spectators.
"""

from kfchess.gateway.router import ConnectionRouter


def a_router(gateway_id="gw1"):
    return ConnectionRouter(gateway_id)


def a_socket():
    """A send callable that keeps what it was given."""
    received = []
    return received.append, received


# --- connections --------------------------------------------------------------

def test_a_connection_id_starts_with_the_gateway_that_minted_it():
    """What makes `conn.{id}` land in this gateway's inbox and in no other's."""
    router = a_router("gw7")
    assert router.open(a_socket()[0]).startswith("gw7.")


def test_connection_ids_are_distinct():
    router = a_router()
    first, second = router.open(a_socket()[0]), router.open(a_socket()[0])
    assert first != second


def test_a_connection_can_be_reached_until_it_closes():
    router = a_router()
    send, received = a_socket()
    conn_id = router.open(send)

    router.to_connection(conn_id)("hello")
    assert received == ["hello"]

    router.close(conn_id)
    assert router.to_connection(conn_id) is None


def test_closing_an_unknown_connection_is_harmless():
    assert a_router().close("gw1.99") == []


def test_the_router_counts_what_it_holds():
    router = a_router()
    first = router.open(a_socket()[0])
    router.open(a_socket()[0])
    assert len(router) == 2

    router.close(first)
    assert len(router) == 1


# --- rooms: one subscription, however many people ------------------------------

def test_the_first_connection_into_a_room_asks_for_a_subscription():
    router = a_router()
    conn_id = router.open(a_socket()[0])
    assert router.follow(conn_id, "4") is True


def test_everyone_after_the_first_rides_the_same_subscription():
    """Two players and three spectators in one room: one subscription, not five."""
    router = a_router()
    conns = [router.open(a_socket()[0]) for _ in range(5)]

    answers = [router.follow(conn_id, "4") for conn_id in conns]

    assert answers == [True, False, False, False, False]


def test_a_room_is_dropped_only_when_its_last_watcher_leaves():
    router = a_router()
    white, black, watcher = [router.open(a_socket()[0]) for _ in range(3)]
    for conn_id in (white, black, watcher):
        router.follow(conn_id, "4")

    assert router.close(white) == []    # the game is still being watched
    assert router.close(black) == []    # by the spectator alone, now
    assert router.close(watcher) == ["4"]  # and now by nobody here


def test_leaving_one_room_does_not_disturb_another():
    router = a_router()
    here, there = router.open(a_socket()[0]), router.open(a_socket()[0])
    router.follow(here, "4")
    router.follow(there, "9")

    assert router.close(here) == ["4"]
    assert router.in_room("9") != []


def test_a_broadcast_reaches_every_watcher_in_the_room():
    router = a_router()
    sockets = [a_socket() for _ in range(3)]
    for send, _ in sockets:
        router.follow(router.open(send), "4")

    for send in router.in_room("4"):
        send("a delta")

    assert [received for _, received in sockets] == [["a delta"]] * 3


def test_a_broadcast_reaches_nobody_in_a_room_this_gateway_has_none_of():
    assert a_router().in_room("4") == []


def test_a_connection_that_closed_before_its_seat_arrived_is_not_followed():
    """The shard's answer and the socket closing can cross; the answer loses."""
    router = a_router()
    conn_id = router.open(a_socket()[0])
    router.close(conn_id)

    assert router.follow(conn_id, "4") is False
    assert router.in_room("4") == []
