"""Tests for the subject vocabulary: the addresses the services agree on.

Small, but worth pinning: a gateway subscribing to one string and a shard publishing to
another is a bug with no error message -- the message simply goes nowhere.
"""

from kfchess.bus import subjects
from kfchess.bus.message_bus import matches


def test_a_gateway_receives_its_own_connections_mail():
    assert matches(subjects.gateway_inbox("gw1"), subjects.connection("gw1.7"))


def test_a_gateway_does_not_receive_another_gateways_mail():
    """What makes a second gateway possible without either knowing about the other."""
    assert not matches(subjects.gateway_inbox("gw2"), subjects.connection("gw1.7"))


def test_a_rooms_inbox_covers_both_its_deltas_and_its_snapshots():
    assert matches(subjects.room_inbox("4"), subjects.room_delta("4"))
    assert matches(subjects.room_inbox("4"), subjects.room_state("4"))


def test_one_rooms_traffic_does_not_reach_another():
    assert not matches(subjects.room_inbox("4"), subjects.room_delta("9"))


def test_the_pre_room_channel_is_one_fixed_subject():
    # Temporary by design: S3 replaces it with Auth, the Matchmaker and the Rooms service.
    assert subjects.LOBBY_CMD == "lobby.cmd"
