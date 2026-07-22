"""Tests for RoomManager: unique room ids mapped to games."""

from kfchess.server.room_manager import RoomManager


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


def test_the_default_id_is_four_uppercase_hex_characters():
    room_id = RoomManager().create(1)
    assert len(room_id) == 4
    assert room_id == room_id.upper()
    assert all(c in "0123456789ABCDEF" for c in room_id)
