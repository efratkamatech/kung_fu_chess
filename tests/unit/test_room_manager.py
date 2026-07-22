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


def test_remove_game_is_a_no_op_for_an_unknown_game():
    rooms = RoomManager(generate_id=sequence("AAAA"))
    rooms.create(7)
    rooms.remove_game(99)  # no room maps to game 99
    assert rooms.game_for("AAAA") == 7
