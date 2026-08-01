"""Tests for the between-process message bus: subject matching and the in-memory fake.

The fake is what every later S2 test runs on, so its matching has to be NATS's matching
and not an approximation of it — a subscription that behaves differently here than in a
deployment would make the whole suite lie.
"""

import pytest

from kfchess.bus import subjects
from kfchess.bus.message_bus import InProcessMessageBus, matches


# --- subject matching ---------------------------------------------------------

@pytest.mark.parametrize(
    "pattern, subject",
    [
        ("lobby.cmd", "lobby.cmd"),                 # no wildcards: itself
        ("conn.gw1.*", "conn.gw1.7"),               # "*" is exactly one token
        ("conn.*.7", "conn.gw1.7"),                 # ...anywhere in the subject
        ("conn.gw1.>", "conn.gw1.7"),               # ">" is one token...
        ("conn.gw1.>", "conn.gw1.7.extra"),         # ...or several
        ("room.4.>", "room.4.delta"),
    ],
)
def test_these_subjects_are_delivered(pattern, subject):
    assert matches(pattern, subject)


@pytest.mark.parametrize(
    "pattern, subject",
    [
        ("lobby.cmd", "lobby.other"),               # a different subject
        ("conn.gw1.*", "conn.gw1.7.extra"),         # "*" is one token, not two
        ("conn.gw1.*", "conn.gw1"),                 # ...and not zero
        ("conn.gw1.>", "conn.gw1"),                 # ">" needs something to match
        ("conn.gw2.>", "conn.gw1.7"),               # another gateway's mail
        ("room.4.>", "room.40.delta"),              # tokens match whole, not by prefix
        ("conn.gw1.7", "conn.gw1"),                 # a shorter subject
    ],
)
def test_these_subjects_are_not(pattern, subject):
    assert not matches(pattern, subject)


# --- the fake bus -------------------------------------------------------------

def test_a_message_reaches_every_matching_subscriber_in_order():
    bus = InProcessMessageBus()
    seen = []
    bus.subscribe("room.4.>", lambda subject, payload: seen.append(("first", payload)))
    bus.subscribe("room.4.delta", lambda subject, payload: seen.append(("second", payload)))
    bus.subscribe("room.9.>", lambda subject, payload: seen.append(("other", payload)))

    bus.publish(subjects.room_delta("4"), "a move")

    assert seen == [("first", "a move"), ("second", "a move")]


def test_a_subscriber_is_told_which_subject_it_was():
    bus = InProcessMessageBus()
    seen = []
    bus.subscribe(subjects.gateway_inbox("gw1"), lambda subject, _: seen.append(subject))

    bus.publish(subjects.connection("gw1.7"), "hello")

    assert seen == ["conn.gw1.7"]  # the wildcard matched, and it knows which connection


def test_a_message_nobody_subscribed_to_is_simply_dropped():
    bus = InProcessMessageBus()
    bus.publish("lobby.cmd", "into the void")
    assert bus.sent_to("lobby.cmd") == ["into the void"]  # recorded, delivered to nobody


def test_unsubscribing_stops_delivery():
    bus = InProcessMessageBus()
    seen = []
    bus.subscribe("room.4.>", lambda subject, payload: seen.append(payload))
    bus.publish(subjects.room_delta("4"), "before")

    bus.unsubscribe("room.4.>")
    bus.publish(subjects.room_delta("4"), "after")

    assert seen == ["before"]


def test_unsubscribing_from_something_never_subscribed_is_harmless():
    bus = InProcessMessageBus()
    bus.unsubscribe("room.99.>")  # e.g. the last member left a room twice over
    bus.publish("room.99.delta", "still fine")
    assert bus.sent_to("room.99.>") == ["still fine"]


def test_the_bus_records_everything_for_a_test_to_read_back():
    bus = InProcessMessageBus()
    bus.publish(subjects.connection("gw1.1"), "to one client")
    bus.publish(subjects.room_delta("4"), "to a room")

    assert bus.published == [("conn.gw1.1", "to one client"), ("room.4.delta", "to a room")]
    assert bus.sent_to(subjects.gateway_inbox("gw1")) == ["to one client"]
    assert bus.sent_to("room.>") == ["to a room"]


# --- queue groups: sharing the work instead of each getting a copy -------------

def test_a_queue_group_delivers_to_exactly_one_member():
    """Why a second shard is possible at all: without this, both run every game."""
    bus = InProcessMessageBus()
    heard = []
    bus.subscribe("lobby.cmd", lambda s, p: heard.append(("sh1", p)), queue_group="shards")
    bus.subscribe("lobby.cmd", lambda s, p: heard.append(("sh2", p)), queue_group="shards")

    bus.publish("lobby.cmd", "hello")

    assert len(heard) == 1


def test_a_queue_group_takes_turns():
    """Shared means shared. Always answering with the first member would hide a bug."""
    bus = InProcessMessageBus()
    heard = []
    for name in ("sh1", "sh2", "sh3"):
        bus.subscribe(
            "lobby.cmd",
            lambda s, p, name=name: heard.append(name),
            queue_group="shards",
        )

    for _ in range(6):
        bus.publish("lobby.cmd", "x")

    assert heard == ["sh1", "sh2", "sh3", "sh1", "sh2", "sh3"]


def test_a_lone_member_of_a_group_gets_everything():
    """The solo server, and any deployment with one shard: nothing is load balanced away."""
    bus = InProcessMessageBus()
    heard = []
    bus.subscribe("lobby.cmd", lambda s, p: heard.append(p), queue_group="shards")

    bus.publish("lobby.cmd", "one")
    bus.publish("lobby.cmd", "two")

    assert heard == ["one", "two"]


def test_subscriptions_outside_a_group_still_all_get_a_copy():
    """Two gateways following one room is a fan-out, not a queue. Both must hear it."""
    bus = InProcessMessageBus()
    heard = []
    bus.subscribe("room.7.delta", lambda s, p: heard.append("gw1"))
    bus.subscribe("room.7.delta", lambda s, p: heard.append("gw2"))

    bus.publish("room.7.delta", "a move")

    assert heard == ["gw1", "gw2"]


def test_a_group_and_a_plain_subscriber_on_the_same_subject_coexist():
    bus = InProcessMessageBus()
    heard = []
    bus.subscribe("lobby.cmd", lambda s, p: heard.append("watcher"))
    bus.subscribe("lobby.cmd", lambda s, p: heard.append("sh1"), queue_group="shards")
    bus.subscribe("lobby.cmd", lambda s, p: heard.append("sh2"), queue_group="shards")

    bus.publish("lobby.cmd", "x")

    assert sorted(heard) == ["sh1", "watcher"]


def test_unsubscribing_drops_a_group_member_too():
    bus = InProcessMessageBus()
    heard = []
    bus.subscribe("lobby.cmd", lambda s, p: heard.append("sh1"), queue_group="shards")

    bus.unsubscribe("lobby.cmd")
    bus.publish("lobby.cmd", "x")

    assert heard == []
