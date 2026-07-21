"""Tests for the synchronous GameServer hub, driven with fake clients (no sockets)."""

from kfchess.config import SOUND_CAPTURE, SOUND_GAME_OVER, SOUND_GAME_START, SOUND_MOVE
from kfchess.model.board import Board
from kfchess.model.color import Color
from kfchess.model.piece import Piece
from kfchess.model.piece_type import standard_piece_types
from kfchess.protocol import Assigned, Event, Login, Move, Rejected, State, encode
from kfchess.server.game_server import GameServer
from kfchess.server.session import GameSession


class FakeClient:
    """Captures the messages the hub sends it (decoded from the wire)."""

    def __init__(self):
        self.received = []

    def send(self, text):
        from kfchess.protocol import decode

        self.received.append(decode(text))


def make_server():
    """A hub over a 3x3 board with a lone white rook at a1."""
    reg = standard_piece_types()
    grid = [
        [None, None, None],
        [None, None, None],
        [Piece(reg.get("R"), Color.WHITE), None, None],
    ]
    return GameServer(GameSession(Board.from_grid(grid)))


def make_king_server():
    """A hub over a 3x3 board: white rook at a1, black king at a3 (capturable)."""
    reg = standard_piece_types()
    grid = [
        [Piece(reg.get("K"), Color.BLACK), None, None],
        [None, None, None],
        [Piece(reg.get("R"), Color.WHITE), None, None],
    ]
    return GameServer(GameSession(Board.from_grid(grid)))


def test_first_two_clients_get_a_colour_and_the_state():
    hub = make_server()
    white, black = FakeClient(), FakeClient()

    hub.connect(white.send)
    hub.connect(black.send)

    assert isinstance(white.received[0], Assigned) and white.received[0].color is Color.WHITE
    assert isinstance(black.received[0], Assigned) and black.received[0].color is Color.BLACK
    assert isinstance(white.received[1], State)


def test_a_third_client_gets_state_but_no_colour():
    hub = make_server()
    hub.connect(FakeClient().send)
    hub.connect(FakeClient().send)
    watcher = FakeClient()

    hub.connect(watcher.send)

    assert not any(isinstance(m, Assigned) for m in watcher.received)
    assert isinstance(watcher.received[0], State)


def test_a_legal_move_broadcasts_the_new_state_to_everyone():
    hub = make_server()
    white, black = FakeClient(), FakeClient()
    hub.connect(white.send)
    hub.connect(black.send)
    before = len(black.received)

    hub.receive(0, encode(Move("WRa1a3")))  # white's client id is 0

    assert isinstance(white.received[-1], State)
    assert len(black.received) == before + 2  # black saw the move event AND the state


def test_an_illegal_move_is_rejected_to_the_sender_only():
    hub = make_server()
    white, black = FakeClient(), FakeClient()
    hub.connect(white.send)
    hub.connect(black.send)
    before_black = len(black.received)

    hub.receive(0, encode(Move("WRa1b2")))  # rooks don't move diagonally

    assert isinstance(white.received[-1], Rejected)
    assert white.received[-1].reason == "illegal_move"
    assert len(black.received) == before_black  # black saw nothing


def test_a_move_from_a_client_with_no_colour_is_rejected():
    hub = make_server()
    hub.connect(FakeClient().send)
    hub.connect(FakeClient().send)
    watcher = FakeClient()
    hub.connect(watcher.send)  # id 2, no colour

    hub.receive(2, encode(Move("WRa1a3")))

    assert isinstance(watcher.received[-1], Rejected)
    assert watcher.received[-1].reason == "not_a_player"


def test_garbage_and_non_move_messages_are_ignored():
    hub = make_server()
    white = FakeClient()
    hub.connect(white.send)
    before = len(white.received)

    hub.receive(0, "not json at all")            # unparseable
    hub.receive(0, encode(Rejected("whatever")))  # a valid message, but not a Move

    assert len(white.received) == before  # nothing sent back


def test_a_disconnected_client_stops_receiving():
    hub = make_server()
    white, black = FakeClient(), FakeClient()
    hub.connect(white.send)
    hub.connect(black.send)
    before_white = len(white.received)

    hub.disconnect(0)  # white leaves
    hub.broadcast_state()

    assert len(white.received) == before_white   # white got nothing more
    assert isinstance(black.received[-1], State)  # black still did


def test_a_message_from_an_unknown_client_is_ignored_safely():
    hub = make_server()
    hub.receive(999, encode(Move("WRa1a3")))  # no such client id -- must not raise


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

    events = [m for m in white.received if isinstance(m, Event)]
    assert events == [Event(SOUND_GAME_START)]


def test_ticking_with_no_clients_does_not_discard_the_game_started_event():
    # Regression: the background ticker calls tick() from server startup, before any
    # client has connected. It must not drain (and so silently lose) the game-started
    # event queued at session creation -- the first connecting client should still see it.
    hub = make_server()
    hub.tick(50)  # as if the ticker fired before anyone connected
    hub.tick(50)
    white = FakeClient()

    hub.connect(white.send)

    events = [m for m in white.received if isinstance(m, Event)]
    assert events == [Event(SOUND_GAME_START)]


def test_a_later_connecting_client_does_not_get_a_duplicate_game_started():
    hub = make_server()
    hub.connect(FakeClient().send)  # drains the one queued game-start event
    black = FakeClient()

    hub.connect(black.send)

    assert not any(isinstance(m, Event) for m in black.received)


def test_a_move_broadcasts_a_move_event_to_every_client_before_the_state():
    hub = make_server()
    white, black = FakeClient(), FakeClient()
    hub.connect(white.send)
    hub.connect(black.send)

    hub.receive(0, encode(Move("WRa1a3")))

    assert black.received[-2] == Event(SOUND_MOVE)
    assert isinstance(black.received[-1], State)


def test_an_illegal_move_broadcasts_no_event():
    hub = make_server()
    white = FakeClient()
    hub.connect(white.send)
    before = len(white.received)

    hub.receive(0, encode(Move("WRa1b2")))  # illegal: rooks don't move diagonally

    assert not any(isinstance(m, Event) for m in white.received[before:])


def test_capturing_the_king_broadcasts_capture_then_game_over_events():
    hub = make_king_server()
    white = FakeClient()
    hub.connect(white.send)

    hub.receive(0, encode(Move("WRa1a3")))  # rook -> king
    hub.tick(100000)                        # rook arrives and captures

    events = [m for m in white.received if isinstance(m, Event)]
    # the initial game-start, then this move's own event, then capture, then game-over
    assert events[-2:] == [Event(SOUND_CAPTURE), Event(SOUND_GAME_OVER)]


# --- login (names) -------------------------------------------------------------

def test_a_login_records_the_name_and_broadcasts_it_to_everyone():
    hub = make_server()
    white, black = FakeClient(), FakeClient()
    hub.connect(white.send)
    hub.connect(black.send)

    hub.receive(0, encode(Login("Efrat")))  # white's client id is 0

    states = [m for m in black.received if isinstance(m, State)]
    assert states[-1].snapshot.names == {Color.WHITE: "Efrat"}


def test_a_login_from_a_spectator_is_ignored():
    hub = make_server()
    hub.connect(FakeClient().send)
    hub.connect(FakeClient().send)
    watcher = FakeClient()
    hub.connect(watcher.send)  # id 2, no colour
    before = len(watcher.received)

    hub.receive(2, encode(Login("Someone")))

    assert len(watcher.received) == before  # nothing sent back, no broadcast triggered


def test_a_second_login_updates_the_other_colour_without_losing_the_first():
    hub = make_server()
    white, black = FakeClient(), FakeClient()
    hub.connect(white.send)
    hub.connect(black.send)

    hub.receive(0, encode(Login("Efrat")))
    hub.receive(1, encode(Login("Dan")))

    states = [m for m in white.received if isinstance(m, State)]
    assert states[-1].snapshot.names == {Color.WHITE: "Efrat", Color.BLACK: "Dan"}
