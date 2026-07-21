"""Tests for the synchronous GameServer hub, driven with fake clients (no sockets)."""

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
from kfchess.protocol import Event, Login, Move, Rejected, State, Welcome, decode, encode
from kfchess.server.game_server import GameServer
from kfchess.server.session import GameSession
from kfchess.server.user_store import UserStore


class FakeClient:
    """Captures the messages the hub sends it (decoded from the wire)."""

    def __init__(self):
        self.received = []

    def send(self, text):
        self.received.append(decode(text))


def make_server():
    """A hub over a 3x3 board with a lone white rook at a1, on a fresh in-memory store."""
    reg = standard_piece_types()
    grid = [
        [None, None, None],
        [None, None, None],
        [Piece(reg.get("R"), Color.WHITE), None, None],
    ]
    return GameServer(GameSession(Board.from_grid(grid)), UserStore(":memory:"))


def make_king_server():
    """A hub over a 3x3 board: white rook at a1, black king at a3 (capturable)."""
    reg = standard_piece_types()
    grid = [
        [Piece(reg.get("K"), Color.BLACK), None, None],
        [None, None, None],
        [Piece(reg.get("R"), Color.WHITE), None, None],
    ]
    return GameServer(GameSession(Board.from_grid(grid)), UserStore(":memory:"))


def login(hub, client_id, username="Efrat", password="pw"):
    """Send a Login message from ``client_id``."""
    hub.receive(client_id, encode(Login(username, password)))


def of_type(client, cls):
    return [m for m in client.received if isinstance(m, cls)]


# --- connecting and logging in ------------------------------------------------

def test_connecting_sends_state_but_no_colour_until_login():
    hub = make_server()
    white = FakeClient()
    hub.connect(white.send)
    assert of_type(white, State)                       # got the board
    assert of_type(white, Welcome) == []               # but no seat yet


def test_the_first_player_to_log_in_gets_white_the_second_black():
    hub = make_server()
    white, black = FakeClient(), FakeClient()
    wid, bid = hub.connect(white.send), hub.connect(black.send)

    login(hub, wid, "Efrat")
    login(hub, bid, "Dan")

    assert of_type(white, Welcome)[-1] == Welcome(Color.WHITE, START_RATING)
    assert of_type(black, Welcome)[-1] == Welcome(Color.BLACK, START_RATING)


def test_logging_in_again_keeps_the_same_seat():
    hub = make_server()
    white = FakeClient()
    wid = hub.connect(white.send)
    login(hub, wid, "Efrat")
    login(hub, wid, "Efrat")  # a second login on the same connection

    assert of_type(white, Welcome)[-1] == Welcome(Color.WHITE, START_RATING)  # still white
    # and it did not burn the black seat: the next player still gets black.
    black = FakeClient()
    bid = hub.connect(black.send)
    login(hub, bid, "Dan")
    assert of_type(black, Welcome)[-1] == Welcome(Color.BLACK, START_RATING)


def test_a_third_player_logs_in_as_a_spectator_with_no_colour():
    hub = make_server()
    a, b, c = FakeClient(), FakeClient(), FakeClient()
    for client in (a, b, c):
        login(hub, hub.connect(client.send))
    assert of_type(c, Welcome)[-1] == Welcome(None, START_RATING)  # a seatless spectator


def test_login_puts_the_name_and_rating_into_the_broadcast_state():
    hub = make_server()
    white, black = FakeClient(), FakeClient()
    wid = hub.connect(white.send)
    hub.connect(black.send)

    login(hub, wid, "Efrat")

    snapshot = of_type(black, State)[-1].snapshot
    assert snapshot.names == {Color.WHITE: "Efrat"}
    assert snapshot.ratings == {Color.WHITE: START_RATING}


def test_a_wrong_password_is_refused_and_can_be_retried_on_the_same_connection():
    hub = make_server()
    first = FakeClient()
    login(hub, hub.connect(first.send), "Efrat", "secret")  # registers Efrat/secret

    second = FakeClient()
    sid = hub.connect(second.send)
    login(hub, sid, "Efrat", "wrong")
    assert second.received[-1] == Rejected("bad_password")
    assert of_type(second, Welcome) == []                  # no seat on a bad password

    login(hub, sid, "Efrat", "secret")                     # retry, same connection
    assert of_type(second, Welcome)[-1] == Welcome(Color.BLACK, START_RATING)


# --- moves (require a logged-in colour) ---------------------------------------

def test_a_move_before_logging_in_is_rejected():
    hub = make_server()
    white = FakeClient()
    wid = hub.connect(white.send)
    hub.receive(wid, encode(Move("WRa1a3")))
    assert white.received[-1] == Rejected("not_a_player")


def test_a_legal_move_broadcasts_an_event_and_state_to_everyone():
    hub = make_server()
    white, black = FakeClient(), FakeClient()
    wid, bid = hub.connect(white.send), hub.connect(black.send)
    login(hub, wid, "Efrat")
    login(hub, bid, "Dan")
    before = len(black.received)

    hub.receive(wid, encode(Move("WRa1a3")))

    assert black.received[-2] == Event(SOUND_MOVE)
    assert isinstance(black.received[-1], State)
    assert len(black.received) == before + 2


def test_an_illegal_move_is_rejected_to_the_sender_only():
    hub = make_server()
    white, black = FakeClient(), FakeClient()
    wid = hub.connect(white.send)
    bid = hub.connect(black.send)
    login(hub, wid, "Efrat")
    login(hub, bid, "Dan")
    before_black = len(black.received)

    hub.receive(wid, encode(Move("WRa1b2")))  # rooks don't move diagonally

    assert white.received[-1] == Rejected("illegal_move")
    assert len(black.received) == before_black  # black saw nothing


def test_a_spectators_move_is_rejected():
    hub = make_server()
    a, b, c = FakeClient(), FakeClient(), FakeClient()
    aid = hub.connect(a.send)
    bid = hub.connect(b.send)
    cid = hub.connect(c.send)
    login(hub, aid)
    login(hub, bid)
    login(hub, cid)  # the spectator, no colour

    hub.receive(cid, encode(Move("WRa1a3")))

    assert c.received[-1] == Rejected("not_a_player")


# --- housekeeping -------------------------------------------------------------

def test_garbage_and_non_login_non_move_messages_are_ignored():
    hub = make_server()
    white = FakeClient()
    wid = hub.connect(white.send)
    before = len(white.received)

    hub.receive(wid, "not json at all")           # unparseable
    hub.receive(wid, encode(Rejected("whatever")))  # valid, but nothing a client sends

    assert len(white.received) == before


def test_a_disconnected_client_stops_receiving():
    hub = make_server()
    white, black = FakeClient(), FakeClient()
    wid = hub.connect(white.send)
    hub.connect(black.send)
    before_white = len(white.received)

    hub.disconnect(wid)
    hub.broadcast_state()

    assert len(white.received) == before_white
    assert isinstance(black.received[-1], State)


def test_a_message_from_an_unknown_client_is_ignored_safely():
    hub = make_server()
    hub.receive(999, encode(Move("WRa1a3")))  # no such client id -- must not raise
    login(hub, 999)                           # a login for a ghost id -- must not raise


def test_tick_advances_and_broadcasts():
    hub = make_server()
    white = FakeClient()
    hub.connect(white.send)
    before = len(white.received)

    hub.tick(10)

    assert len(white.received) == before + 1
    assert isinstance(white.received[-1], State)


# --- immediate-reaction events (sound) ----------------------------------------

def test_the_first_connecting_client_hears_the_game_started_event():
    hub = make_server()
    white = FakeClient()
    hub.connect(white.send)
    assert of_type(white, Event) == [Event(SOUND_GAME_START)]


def test_ticking_with_no_clients_does_not_discard_the_game_started_event():
    # Regression: the background ticker calls tick() from server startup, before any
    # client has connected. It must not drain (and so silently lose) the game-started
    # event queued at session creation -- the first connecting client should still see it.
    hub = make_server()
    hub.tick(50)
    hub.tick(50)
    white = FakeClient()
    hub.connect(white.send)
    assert of_type(white, Event) == [Event(SOUND_GAME_START)]


def test_a_later_connecting_client_does_not_get_a_duplicate_game_started():
    hub = make_server()
    hub.connect(FakeClient().send)  # drains the one queued game-start event
    black = FakeClient()
    hub.connect(black.send)
    assert of_type(black, Event) == []


def test_capturing_the_king_broadcasts_capture_then_game_over_events():
    hub = make_king_server()
    white = FakeClient()
    wid = hub.connect(white.send)
    login(hub, wid, "Efrat")

    hub.receive(wid, encode(Move("WRa1a3")))  # rook -> king
    hub.tick(100000)                          # rook arrives and captures

    events = of_type(white, Event)
    assert events[-2:] == [Event(SOUND_CAPTURE), Event(SOUND_GAME_OVER)]


# --- ELO update on game over --------------------------------------------------

def test_a_finished_game_updates_both_ratings_once_and_shows_them():
    hub = make_king_server()
    white, black = FakeClient(), FakeClient()
    wid, bid = hub.connect(white.send), hub.connect(black.send)
    login(hub, wid, "Efrat")   # white
    login(hub, bid, "Dan")     # black

    hub.receive(wid, encode(Move("WRa1a3")))  # rook -> black king
    hub.tick(100000)                          # capture -> game over -> ELO update

    assert hub._users.get_rating("Efrat") == 1216   # winner up
    assert hub._users.get_rating("Dan") == 1184     # loser down
    snapshot = of_type(white, State)[-1].snapshot
    assert snapshot.ratings == {Color.WHITE: 1216, Color.BLACK: 1184}

    hub.tick(100000)  # a further tick must not apply the update a second time
    assert hub._users.get_rating("Efrat") == 1216


def test_a_game_that_ends_without_two_known_players_is_not_rated():
    hub = make_king_server()
    white = FakeClient()
    wid = hub.connect(white.send)
    login(hub, wid, "Efrat")  # only white logged in; nobody is black

    hub.receive(wid, encode(Move("WRa1a3")))
    hub.tick(100000)          # white captures the unowned black king -> game over

    assert hub._users.get_rating("Efrat") == START_RATING  # unrated: no opponent
