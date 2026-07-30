"""Tests for the player directory: one lookup instead of a search, and a real token."""

from kfchess.model.color import Color
from kfchess.services.directory import PlayerDirectory, Seat, mint_token
from kfchess.services.store import InMemoryKeyValueStore


def a_directory(tokens=("token-1", "token-2", "token-3"), clock=None):
    """A directory over a fake store, handing out known tokens in order."""
    remaining = list(tokens)
    now = clock if clock is not None else [0.0]
    store = InMemoryKeyValueStore(lambda: now[0])
    return PlayerDirectory(store, new_token=lambda: remaining.pop(0)), now


def test_a_seat_reads_back_exactly_as_it_was_taken():
    directory, _ = a_directory()

    seat = directory.take_seat("Efrat", "AAAAAA", "sh1", Color.WHITE)

    assert seat == Seat("AAAAAA", "sh1", Color.WHITE, "token-1")
    assert directory.seat_of("Efrat") == seat  # and it survived the round trip as JSON


def test_a_player_nobody_seated_is_sitting_nowhere():
    directory, _ = a_directory()
    assert directory.seat_of("Efrat") is None


def test_each_seat_gets_its_own_token():
    """Two players in the same room may not share the proof of who they are."""
    directory, _ = a_directory()

    white = directory.take_seat("Efrat", "AAAAAA", "sh1", Color.WHITE)
    black = directory.take_seat("Dan", "AAAAAA", "sh1", Color.BLACK)

    assert white.seat_token != black.seat_token


def test_the_directory_knows_which_shard_is_running_the_room():
    """What replaces the scan: the answer names the machine, not just the room."""
    directory, _ = a_directory()
    directory.take_seat("Efrat", "AAAAAA", "sh7", Color.BLACK)

    assert directory.seat_of("Efrat").shard_id == "sh7"
    assert directory.seat_of("Efrat").color is Color.BLACK


def test_leaving_a_seat_forgets_it():
    directory, _ = a_directory()
    directory.take_seat("Efrat", "AAAAAA", "sh1", Color.WHITE)

    directory.leave("Efrat")

    assert directory.seat_of("Efrat") is None


def test_leaving_a_seat_nobody_holds_is_harmless():
    directory, _ = a_directory()
    directory.leave("Efrat")  # her game ended before she was ever seated
    assert directory.seat_of("Efrat") is None


def test_a_seat_a_crashed_shard_left_behind_expires_on_its_own():
    """Nothing tidies up after a shard that dies; the entry has to stop being true."""
    now = [0.0]
    directory, _ = a_directory(clock=now)
    directory.take_seat("Efrat", "AAAAAA", "sh1", Color.WHITE)

    now[0] = 301.0

    assert directory.seat_of("Efrat") is None


def test_taking_a_new_seat_replaces_the_old_one():
    directory, _ = a_directory()
    directory.take_seat("Efrat", "AAAAAA", "sh1", Color.WHITE)

    directory.take_seat("Efrat", "BBBBBB", "sh2", Color.BLACK)

    seat = directory.seat_of("Efrat")
    assert (seat.room_id, seat.shard_id, seat.color) == ("BBBBBB", "sh2", Color.BLACK)


# --- the token itself ----------------------------------------------------------

def test_a_minted_token_is_long_and_unguessable():
    first, second = mint_token(), mint_token()
    assert first != second
    assert len(first) == 32  # SEAT_TOKEN_BYTES=16, hex-encoded
    assert all(character in "0123456789abcdef" for character in first)
