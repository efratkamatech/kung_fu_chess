"""Tests for the rooms service: ids unique across shards, not merely across one.

Two halves, because the class answers two different questions. The local half — which of
my games is this room — is what the single-process ``RoomManager`` did, and every one of
its tests is still here, because none of that behaviour was allowed to change. The shared
half is the reason the class exists: being safe when two shards claim the same id at the
same instant is a property a dictionary cannot have.
"""

import pytest

from kfchess.config import ROOM_ID_ALPHABET, ROOM_ID_LENGTH, ROOM_ID_MAX_ATTEMPTS
from kfchess.services.rooms import RoomIdUnavailable, Rooms
from kfchess.services.store import InMemoryKeyValueStore


def a_store(clock=None):
    now = clock if clock is not None else [0.0]
    return InMemoryKeyValueStore(lambda: now[0]), now


def ids(*sequence):
    """An id generator handing back known values, so collisions can be forced."""
    remaining = list(sequence)
    return lambda: remaining.pop(0)


# --- the local map: which of my games a room is --------------------------------

def test_create_registers_the_game_under_a_new_id():
    rooms = Rooms(generate_id=ids("7C2FQK"))

    assert rooms.create(game_id=3) == "7C2FQK"
    assert rooms.game_for("7C2FQK") == 3


def test_game_for_an_unknown_room_is_none():
    assert Rooms().game_for("ZZZZZZ") is None


def test_create_regenerates_the_id_on_a_collision():
    rooms = Rooms(generate_id=ids("AAAAAA", "AAAAAA", "BBBBBB"))

    assert rooms.create(1) == "AAAAAA"
    assert rooms.create(2) == "BBBBBB"  # the second "AAAAAA" collided, so it tried again
    assert rooms.game_for("AAAAAA") == 1
    assert rooms.game_for("BBBBBB") == 2


def test_remove_game_forgets_its_room():
    rooms = Rooms(generate_id=ids("AAAAAA"))
    rooms.create(7)

    rooms.remove_game(7)

    assert rooms.game_for("AAAAAA") is None


def test_remove_game_leaves_other_rooms_untouched():
    rooms = Rooms(generate_id=ids("AAAAAA", "BBBBBB"))
    rooms.create(7)
    rooms.create(8)

    rooms.remove_game(7)

    assert rooms.game_for("AAAAAA") is None
    assert rooms.game_for("BBBBBB") == 8  # a different game's room survives


def test_remove_game_is_a_no_op_for_an_unknown_game():
    rooms = Rooms(generate_id=ids("AAAAAA"))
    rooms.create(7)

    rooms.remove_game(99)  # no room maps to game 99

    assert rooms.game_for("AAAAAA") == 7


def test_the_default_store_is_this_process():
    """A ``Rooms()`` with nothing injected works, which is what the solo server is."""
    rooms = Rooms(generate_id=ids("AAAAAA"))

    assert rooms.create(1) == "AAAAAA"
    assert rooms.shard_of("AAAAAA") is not None  # claimed, in a store of its own


def test_the_default_generator_is_read_aloud_safe():
    room_id = Rooms().create(1)

    assert len(room_id) == ROOM_ID_LENGTH
    assert all(character in ROOM_ID_ALPHABET for character in room_id)
    # The characters a player could confuse when copying an id off a screen are out.
    assert not set(room_id) & set("OILU")


# --- the shared claim: the property a dictionary could not have ----------------

def test_a_created_room_is_registered_to_the_shard_that_made_it():
    store, _ = a_store()
    rooms = Rooms(store, "sh1", generate_id=ids("7C2FQK"))

    rooms.create(3)

    assert rooms.shard_of("7C2FQK") == "sh1"


def test_a_room_nobody_opened_is_running_nowhere():
    store, _ = a_store()

    assert Rooms(store, "sh1").shard_of("ZZZZZZ") is None


def test_two_shards_drawing_the_same_id_do_not_both_get_it():
    """The whole point: one store, one claim, and the loser is told."""
    store, _ = a_store()
    here = Rooms(store, "sh1", generate_id=ids("AAAAAA"))
    there = Rooms(store, "sh2", generate_id=ids("AAAAAA", "BBBBBB"))

    assert here.create(1) == "AAAAAA"
    assert there.create(1) == "BBBBBB"  # it collided and drew again

    assert here.shard_of("AAAAAA") == "sh1"  # the first claim stands
    assert there.shard_of("BBBBBB") == "sh2"


def test_each_shard_only_knows_its_own_games_behind_a_shared_id():
    """A joiner on the wrong shard gets no game, and is told where to look instead."""
    store, _ = a_store()
    elsewhere = Rooms(store, "sh2", generate_id=ids("7C2FQK"))
    elsewhere.create(4)

    asking_shard = Rooms(store, "sh1")

    assert asking_shard.game_for("7C2FQK") is None   # not one of mine
    assert asking_shard.shard_of("7C2FQK") == "sh2"  # but it is somebody's


def test_an_id_held_by_a_crashed_shard_frees_itself():
    store, now = a_store()
    Rooms(store, "sh1", generate_id=ids("AAAAAA")).create(1)  # ...and sh1 dies here

    now[0] = 301.0

    survivor = Rooms(store, "sh2", generate_id=ids("AAAAAA"))
    assert survivor.create(1) == "AAAAAA"
    assert survivor.shard_of("AAAAAA") == "sh2"


def test_a_finished_game_releases_its_id_for_everyone():
    """Removal drops all three records, so another shard can have the id at once."""
    store, _ = a_store()
    here = Rooms(store, "sh1", generate_id=ids("AAAAAA"))
    here.create(7)

    here.remove_game(7)

    assert here.shard_of("AAAAAA") is None
    assert Rooms(store, "sh2", generate_id=ids("AAAAAA")).create(1) == "AAAAAA"


def test_creating_gives_up_rather_than_spinning_for_ever():
    """The hang fix, now against a claim another shard is holding."""
    store, _ = a_store()
    Rooms(store, "sh1", generate_id=ids("AAAAAA")).create(1)  # the only id there is
    stuck = Rooms(store, "sh2", generate_id=lambda: "AAAAAA")

    with pytest.raises(RoomIdUnavailable):
        stuck.create(2)


def test_it_gives_up_after_the_configured_number_of_tries():
    store, _ = a_store()
    Rooms(store, "sh1", generate_id=ids("AAAAAA")).create(1)
    attempts = []

    def always_taken():
        attempts.append("AAAAAA")
        return "AAAAAA"

    with pytest.raises(RoomIdUnavailable):
        Rooms(store, "sh2", generate_id=always_taken).create(2)

    assert len(attempts) == ROOM_ID_MAX_ATTEMPTS


def test_no_id_is_handed_out_twice_however_many_shards_are_drawing():
    """The exit criterion, made hostile: fifty shards drawing from an alphabet of five.

    Collisions are certain rather than unlikely here, which is the point — a dictionary
    per process would sail through this test and hand the same id to a dozen players.
    Every claim goes through one store, so the ids that come back are all different and
    the shards that could not get one are told so rather than quietly sharing.
    """
    store, _ = a_store()
    alphabet = "ABCDE"
    draws = iter(alphabet * 200)  # every shard walks the same tiny space, in the same order
    shards = [
        Rooms(store, f"sh{index}", generate_id=lambda: next(draws)) for index in range(50)
    ]

    claimed, refused = [], 0
    for game_id, shard in enumerate(shards):
        try:
            claimed.append(shard.create(game_id))
        except RoomIdUnavailable:
            refused += 1

    assert len(claimed) == len(set(claimed))  # nobody got somebody else's id
    assert sorted(claimed) == sorted(alphabet)  # and the space was used up, not wasted
    assert refused == len(shards) - len(alphabet)
    for room_id in claimed:
        assert store.get(f"room:{room_id}") is not None  # each claim is on the record
