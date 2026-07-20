"""Tests for the synchronous GameServer hub, driven with fake clients (no sockets)."""

from kfchess.model.board import Board
from kfchess.model.color import Color
from kfchess.model.piece import Piece
from kfchess.model.piece_type import standard_piece_types
from kfchess.protocol import Assigned, Move, Rejected, State, encode
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
    assert len(black.received) == before + 1  # black saw the move too


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
