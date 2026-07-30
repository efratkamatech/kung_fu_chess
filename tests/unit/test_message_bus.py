"""Tests for the between-process message bus: subject matching and the in-memory fake.

The fake is what every later S2 test runs on, so its matching has to be NATS's matching
and not an approximation of it — a subscription that behaves differently here than in a
deployment would make the whole suite lie.
"""

import pytest

from kfchess.bus import subjects
from kfchess.bus.message_bus import FakeMessageBus, matches


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
    bus = FakeMessageBus()
    seen = []
    bus.subscribe("room.4.>", lambda subject, payload: seen.append(("first", payload)))
    bus.subscribe("room.4.delta", lambda subject, payload: seen.append(("second", payload)))
    bus.subscribe("room.9.>", lambda subject, payload: seen.append(("other", payload)))

    bus.publish(subjects.room_delta("4"), "a move")

    assert seen == [("first", "a move"), ("second", "a move")]


def test_a_subscriber_is_told_which_subject_it_was():
    bus = FakeMessageBus()
    seen = []
    bus.subscribe(subjects.gateway_inbox("gw1"), lambda subject, _: seen.append(subject))

    bus.publish(subjects.connection("gw1.7"), "hello")

    assert seen == ["conn.gw1.7"]  # the wildcard matched, and it knows which connection


def test_a_message_nobody_subscribed_to_is_simply_dropped():
    bus = FakeMessageBus()
    bus.publish("lobby.cmd", "into the void")
    assert bus.sent_to("lobby.cmd") == ["into the void"]  # recorded, delivered to nobody


def test_unsubscribing_stops_delivery():
    bus = FakeMessageBus()
    seen = []
    bus.subscribe("room.4.>", lambda subject, payload: seen.append(payload))
    bus.publish(subjects.room_delta("4"), "before")

    bus.unsubscribe("room.4.>")
    bus.publish(subjects.room_delta("4"), "after")

    assert seen == ["before"]


def test_unsubscribing_from_something_never_subscribed_is_harmless():
    bus = FakeMessageBus()
    bus.unsubscribe("room.99.>")  # e.g. the last member left a room twice over
    bus.publish("room.99.delta", "still fine")
    assert bus.sent_to("room.99.>") == ["still fine"]


def test_the_bus_records_everything_for_a_test_to_read_back():
    bus = FakeMessageBus()
    bus.publish(subjects.connection("gw1.1"), "to one client")
    bus.publish(subjects.room_delta("4"), "to a room")

    assert bus.published == [("conn.gw1.1", "to one client"), ("room.4.delta", "to a room")]
    assert bus.sent_to(subjects.gateway_inbox("gw1")) == ["to one client"]
    assert bus.sent_to("room.>") == ["to a room"]
