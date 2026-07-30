"""Tests for the rooms service: ids unique across shards, not merely across one.

The test that matters is the concurrent one. Everything else here also held when rooms
lived in a dictionary; being safe when two shards claim at the same instant is the reason
this class exists.
"""

import pytest

from kfchess.config import ROOM_ID_MAX_ATTEMPTS
from kfchess.server.room_manager import RoomIdUnavailable
from kfchess.services.rooms import Rooms
from kfchess.services.store import InMemoryKeyValueStore


def a_store(clock=None):
    now = clock if clock is not None else [0.0]
    return InMemoryKeyValueStore(lambda: now[0]), now


def ids(*sequence):
    """An id generator handing back known values, so collisions can be forced."""
    remaining = list(sequence)
    return lambda: remaining.pop(0)


def test_a_created_room_is_registered_to_the_shard_that_made_it():
    store, _ = a_store()
    rooms = Rooms(store, "sh1", generate_id=ids("7C2FQK"))

    assert rooms.create() == "7C2FQK"
    assert rooms.shard_of("7C2FQK") == "sh1"


def test_a_room_nobody_opened_is_running_nowhere():
    store, _ = a_store()
    assert Rooms(store, "sh1").shard_of("ZZZZZZ") is None


def test_a_closed_room_is_forgotten():
    store, _ = a_store()
    rooms = Rooms(store, "sh1", generate_id=ids("7C2FQK"))
    rooms.create()

    rooms.close("7C2FQK")

    assert rooms.shard_of("7C2FQK") is None


# --- the property a dictionary could not have ----------------------------------

def test_two_shards_drawing_the_same_id_do_not_both_get_it():
    """The whole point: one store, one claim, and the loser is told."""
    store, _ = a_store()
    here = Rooms(store, "sh1", generate_id=ids("AAAAAA"))
    there = Rooms(store, "sh2", generate_id=ids("AAAAAA", "BBBBBB"))

    assert here.create() == "AAAAAA"
    assert there.create() == "BBBBBB"  # it collided and drew again

    assert store.get("room:AAAAAA") == "sh1"  # the first claim stands
    assert store.get("room:BBBBBB") == "sh2"


def test_a_joiner_is_told_which_shard_is_running_a_room_it_cannot_see():
    """What a second shard needs in order to route somebody to a room it does not hold."""
    store, _ = a_store()
    elsewhere = Rooms(store, "sh2", generate_id=ids("7C2FQK"))
    elsewhere.create()

    asking_shard = Rooms(store, "sh1")

    assert asking_shard.shard_of("7C2FQK") == "sh2"


def test_an_id_held_by_a_crashed_shard_frees_itself():
    store, now = a_store()
    Rooms(store, "sh1", generate_id=ids("AAAAAA")).create()  # ...and sh1 dies here

    now[0] = 301.0

    assert Rooms(store, "sh2", generate_id=ids("AAAAAA")).create() == "AAAAAA"
    assert store.get("room:AAAAAA") == "sh2"


def test_creating_gives_up_rather_than_spinning_for_ever():
    store, _ = a_store()
    Rooms(store, "sh1", generate_id=ids("AAAAAA")).create()  # the only id there is
    stuck = Rooms(store, "sh2", generate_id=lambda: "AAAAAA")

    with pytest.raises(RoomIdUnavailable):
        stuck.create()


def test_it_gives_up_after_the_configured_number_of_tries():
    store, _ = a_store()
    Rooms(store, "sh1", generate_id=ids("AAAAAA")).create()
    attempts = []

    def always_taken():
        attempts.append("AAAAAA")
        return "AAAAAA"

    with pytest.raises(RoomIdUnavailable):
        Rooms(store, "sh2", generate_id=always_taken).create()

    assert len(attempts) == ROOM_ID_MAX_ATTEMPTS


def test_the_default_generator_is_the_read_aloud_safe_one():
    """The same alphabet the single-process manager used; ids did not get worse."""
    from kfchess.config import ROOM_ID_ALPHABET, ROOM_ID_LENGTH

    store, _ = a_store()
    room_id = Rooms(store, "sh1").create()

    assert len(room_id) == ROOM_ID_LENGTH
    assert all(character in ROOM_ID_ALPHABET for character in room_id)
