"""Tests for RoomManager: unique room ids mapped to games."""

import pytest

from kfchess.config import ROOM_ID_ALPHABET, ROOM_ID_LENGTH, ROOM_ID_MAX_ATTEMPTS
from kfchess.server.room_manager import RoomIdUnavailable, RoomManager


def sequence(*ids):
    """A generator that hands back each id in turn (to force known values/collisions)."""
    remaining = list(ids)
    return lambda: remaining.pop(0)


def test_create_registers_the_game_under_a_new_id():
    rooms = RoomManager(generate_id=sequence("7C2F"))
    room_id = rooms.create(game_id=3)
    assert room_id == "7C2F"
    assert rooms.game_for("7C2F") == 3


def test_game_for_an_unknown_room_is_none():
    assert RoomManager().game_for("ZZZZ") is None


def test_create_regenerates_the_id_on_a_collision():
    rooms = RoomManager(generate_id=sequence("AAAA", "AAAA", "BBBB"))
    assert rooms.create(1) == "AAAA"
    assert rooms.create(2) == "BBBB"  # the second "AAAA" collided, so it tried again
    assert rooms.game_for("AAAA") == 1
    assert rooms.game_for("BBBB") == 2


def test_the_default_id_is_read_aloud_safe():
    room_id = RoomManager().create(1)
    assert len(room_id) == ROOM_ID_LENGTH
    assert all(c in ROOM_ID_ALPHABET for c in room_id)
    # The characters a player could confuse when copying an id off a screen are out.
    assert not set(room_id) & set("OILU")


def test_create_gives_up_rather_than_spinning_for_ever():
    """The hang fix: an id space that never yields a free id must end the attempt."""
    attempts = []

    def always_the_same():
        attempts.append("AAAAAA")
        return "AAAAAA"

    rooms = RoomManager(generate_id=always_the_same)
    assert rooms.create(1) == "AAAAAA"          # the first one is free
    with pytest.raises(RoomIdUnavailable):
        rooms.create(2)                          # every later one collides
    assert len(attempts) == 1 + ROOM_ID_MAX_ATTEMPTS
    assert rooms.game_for("AAAAAA") == 1         # and the first room is untouched


def test_remove_game_forgets_its_room():
    rooms = RoomManager(generate_id=sequence("AAAA"))
    rooms.create(7)
    rooms.remove_game(7)
    assert rooms.game_for("AAAA") is None


def test_remove_game_leaves_other_rooms_untouched():
    rooms = RoomManager(generate_id=sequence("AAAA", "BBBB"))
    rooms.create(7)
    rooms.create(8)
    rooms.remove_game(7)
    assert rooms.game_for("AAAA") is None
    assert rooms.game_for("BBBB") == 8  # a different game's room survives


def test_a_removed_id_can_be_handed_out_again():
    """Removal drops both directions, so the id is genuinely free afterwards."""
    rooms = RoomManager(generate_id=sequence("AAAA", "AAAA"))
    rooms.create(7)
    rooms.remove_game(7)
    assert rooms.create(8) == "AAAA"  # no collision: the old mapping is really gone
    assert rooms.game_for("AAAA") == 8


def test_remove_game_is_a_no_op_for_an_unknown_game():
    rooms = RoomManager(generate_id=sequence("AAAA"))
    rooms.create(7)
    rooms.remove_game(99)  # no room maps to game 99
    assert rooms.game_for("AAAA") == 7
