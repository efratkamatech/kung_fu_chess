"""Tests for the Lobby hub: login, matchmaking, routing, and per-game broadcast.

Driven with fake ``send`` callbacks (no sockets). Two clients with equal starting
ratings are always within the matchmaking window, so "log in and press Play on both"
is the standard way to get a running game.
"""

import asyncio

from kfchess.config import (
    SOUND_CAPTURE,
    SOUND_GAME_OVER,
    SOUND_GAME_START,
    SOUND_MOVE,
    START_RATING,
)
from kfchess.model.board import Board
from kfchess.model.color import Color
from kfchess.model.piece import Piece
from kfchess.model.piece_type import standard_piece_types
from kfchess.protocol import (
    Event,
    Login,
    Move,
    Notice,
    Play,
    Rejected,
    Seated,
    State,
    Welcome,
    decode,
    encode,
)
from kfchess.server.game_server import serve
from kfchess.server.lobby import Lobby
from kfchess.server.user_store import UserStore


class FakeClient:
    """Captures the messages the hub sends it (decoded from the wire)."""

    def __init__(self):
        self.received = []

    def send(self, text):
        self.received.append(decode(text))


def _rook_board():
    """A 3x3 board with a lone white rook at a1."""
    reg = standard_piece_types()
    grid = [
        [None, None, None],
        [None, None, None],
        [Piece(reg.get("R"), Color.WHITE), None, None],
    ]
    return Board.from_grid(grid)


def _king_board():
    """A 3x3 board: white rook at a1, black king at a3 (capturable)."""
    reg = standard_piece_types()
    grid = [
        [Piece(reg.get("K"), Color.BLACK), None, None],
        [None, None, None],
        [Piece(reg.get("R"), Color.WHITE), None, None],
    ]
    return Board.from_grid(grid)


def make_lobby(new_board=_rook_board):
    """A lobby that hands out ``new_board`` copies, on a fresh in-memory user store."""
    return Lobby(new_board, UserStore(":memory:"))


def login(hub, client_id, username="Efrat", password="pw"):
    hub.receive(client_id, encode(Login(username, password)))


def of_type(client, cls):
    return [m for m in client.received if isinstance(m, cls)]


def seat_two(new_board=_rook_board):
    """Log in two clients and match them; returns the hub, both clients, and their ids."""
    hub = make_lobby(new_board)
    white, black = FakeClient(), FakeClient()
    wid, bid = hub.connect(white.send), hub.connect(black.send)
    login(hub, wid, "Efrat")
    login(hub, bid, "Dan")
    hub.receive(wid, encode(Play()))  # first: waits
    hub.receive(bid, encode(Play()))  # second: matches -> a game starts
    return hub, white, black, wid, bid


# --- connecting and logging in ------------------------------------------------

def test_connecting_sends_nothing_until_you_act():
    hub = make_lobby()
    client = FakeClient()
    hub.connect(client.send)
    assert client.received == []  # no board, no seat -- you are only "connected"


def test_login_welcomes_you_into_the_lobby_with_no_seat():
    hub = make_lobby()
    client = FakeClient()
    login(hub, hub.connect(client.send), "Efrat")
    assert of_type(client, Welcome)[-1] == Welcome(None, START_RATING)  # in the lobby


def test_a_wrong_password_is_refused_and_can_be_retried():
    hub = make_lobby()
    first = FakeClient()
    login(hub, hub.connect(first.send), "Efrat", "secret")  # registers Efrat/secret

    second = FakeClient()
    sid = hub.connect(second.send)
    login(hub, sid, "Efrat", "wrong")
    assert second.received[-1] == Rejected("bad_password")
    assert of_type(second, Welcome) == []

    login(hub, sid, "Efrat", "secret")  # retry, same connection
    assert of_type(second, Welcome)[-1] == Welcome(None, START_RATING)


# --- matchmaking --------------------------------------------------------------

def test_two_logged_in_players_who_press_play_are_matched():
    _, white, black, _, _ = seat_two()
    assert of_type(white, Seated)[-1] == Seated(Color.WHITE)  # first to seek gets white
    assert of_type(black, Seated)[-1] == Seated(Color.BLACK)


def test_a_matched_game_shows_both_players_the_board_and_start_sound():
    _, white, black, _, _ = seat_two()
    for client in (white, black):
        assert of_type(client, State)  # each got the starting snapshot
        assert of_type(client, Event) == [Event(SOUND_GAME_START)]


def test_the_matched_snapshot_carries_both_names_and_ratings():
    _, white, _, _, _ = seat_two()
    snapshot = of_type(white, State)[-1].snapshot
    assert snapshot.names == {Color.WHITE: "Efrat", Color.BLACK: "Dan"}
    assert snapshot.ratings == {Color.WHITE: START_RATING, Color.BLACK: START_RATING}


def test_a_lone_seeker_waits_and_is_not_seated():
    hub = make_lobby()
    client = FakeClient()
    cid = hub.connect(client.send)
    login(hub, cid, "Efrat")
    hub.receive(cid, encode(Play()))
    assert of_type(client, Seated) == []  # nobody to match with yet


def test_play_before_logging_in_is_ignored():
    hub = make_lobby()
    client = FakeClient()
    cid = hub.connect(client.send)
    hub.receive(cid, encode(Play()))  # no login first -- must not seat or crash
    assert of_type(client, Seated) == []


def test_pressing_play_twice_while_waiting_does_not_pair_you_with_yourself():
    hub = make_lobby()
    client = FakeClient()
    cid = hub.connect(client.send)
    login(hub, cid, "Efrat")
    hub.receive(cid, encode(Play()))
    hub.receive(cid, encode(Play()))  # second press: still just waiting
    assert of_type(client, Seated) == []


def test_pressing_play_again_while_already_in_a_game_is_ignored():
    hub, white, _, wid, _ = seat_two()
    before = len(white.received)
    hub.receive(wid, encode(Play()))  # already seated
    assert len(white.received) == before


def test_a_lone_seeker_is_told_no_opponent_after_the_timeout():
    from kfchess.config import MATCH_TIMEOUT_MS

    hub = make_lobby()
    client = FakeClient()
    cid = hub.connect(client.send)
    login(hub, cid, "Efrat")
    hub.receive(cid, encode(Play()))
    hub.tick(MATCH_TIMEOUT_MS)
    assert of_type(client, Notice)[-1] == Notice("no_opponent")


# --- moves and routing --------------------------------------------------------

def test_a_move_before_being_in_a_game_is_rejected():
    hub = make_lobby()
    client = FakeClient()
    cid = hub.connect(client.send)
    login(hub, cid, "Efrat")  # in the lobby, but not in a game
    hub.receive(cid, encode(Move("WRa1a3")))
    assert client.received[-1] == Rejected("not_a_player")


def test_a_legal_move_broadcasts_an_event_and_state_to_both_players():
    hub, white, black, wid, _ = seat_two()
    before = len(black.received)

    hub.receive(wid, encode(Move("WRa1a3")))

    assert black.received[-2] == Event(SOUND_MOVE)
    assert isinstance(black.received[-1], State)
    assert len(black.received) == before + 2


def test_an_illegal_move_is_rejected_to_the_sender_only():
    hub, white, black, wid, _ = seat_two()
    before_black = len(black.received)

    hub.receive(wid, encode(Move("WRa1b2")))  # rooks don't move diagonally

    assert white.received[-1] == Rejected("illegal_move")
    assert len(black.received) == before_black  # black saw nothing


def test_two_games_run_in_parallel_without_crossing_broadcasts():
    hub = make_lobby()
    a, b, c, d = FakeClient(), FakeClient(), FakeClient(), FakeClient()
    ids = [hub.connect(x.send) for x in (a, b, c, d)]
    for cid, name in zip(ids, ("A", "B", "C", "D")):
        login(hub, cid, name)
    hub.receive(ids[0], encode(Play()))
    hub.receive(ids[1], encode(Play()))  # A+B -> game one
    hub.receive(ids[2], encode(Play()))
    hub.receive(ids[3], encode(Play()))  # C+D -> game two

    before_c, before_d = len(c.received), len(d.received)
    hub.receive(ids[0], encode(Move("WRa1a3")))  # a move in game one

    assert isinstance(a.received[-1], State) and isinstance(b.received[-1], State)
    assert len(c.received) == before_c  # game two saw nothing
    assert len(d.received) == before_d


# --- housekeeping -------------------------------------------------------------

def test_garbage_and_non_client_messages_are_ignored():
    hub = make_lobby()
    client = FakeClient()
    cid = hub.connect(client.send)
    before = len(client.received)
    hub.receive(cid, "not json at all")            # unparseable
    hub.receive(cid, encode(Rejected("whatever")))  # valid, but not a client message
    assert len(client.received) == before


def test_a_message_from_an_unknown_client_is_ignored_safely():
    hub = make_lobby()
    hub.receive(999, encode(Move("WRa1a3")))  # no such client id -- must not raise


def test_disconnecting_a_waiting_seeker_removes_them_from_the_queue():
    hub = make_lobby()
    lone, other = FakeClient(), FakeClient()
    lid = hub.connect(lone.send)
    login(hub, lid, "Efrat")
    hub.receive(lid, encode(Play()))  # lone is now waiting
    hub.disconnect(lid)

    oid = hub.connect(other.send)
    login(hub, oid, "Dan")
    hub.receive(oid, encode(Play()))
    assert of_type(other, Seated) == []  # the disconnected seeker was not matched


def test_ticking_a_game_whose_players_all_left_does_not_crash():
    hub, white, black, wid, bid = seat_two()
    hub.disconnect(wid)
    hub.disconnect(bid)
    hub.tick(10)  # the game has no members left -- must tick without error


# --- game over and ELO --------------------------------------------------------

def test_capturing_the_king_broadcasts_capture_then_game_over():
    hub, white, _, wid, _ = seat_two(_king_board)
    hub.receive(wid, encode(Move("WRa1a3")))  # rook -> black king
    hub.tick(100000)                          # rook arrives and captures

    events = of_type(white, Event)
    assert events[-2:] == [Event(SOUND_CAPTURE), Event(SOUND_GAME_OVER)]


def test_a_finished_game_updates_both_ratings_once_and_shows_them():
    hub, white, _, wid, _ = seat_two(_king_board)

    hub.receive(wid, encode(Move("WRa1a3")))  # rook -> black king
    hub.tick(100000)                          # capture -> game over -> ELO update

    assert hub._users.get_rating("Efrat") == 1216  # winner up
    assert hub._users.get_rating("Dan") == 1184     # loser down
    snapshot = of_type(white, State)[-1].snapshot
    assert snapshot.ratings == {Color.WHITE: 1216, Color.BLACK: 1184}

    hub.tick(100000)  # a further tick must not apply the update a second time
    assert hub._users.get_rating("Efrat") == 1216


# --- the async entry point is importable --------------------------------------

def test_serve_is_an_async_entry_point():
    assert asyncio.iscoroutinefunction(serve)
