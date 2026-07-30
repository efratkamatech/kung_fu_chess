"""A gateway and a shard, wired together over the bus, playing a whole game.

This is the test S2 exists to make pass. Two processes' worth of code — sockets on one
side, games on the other, nothing shared but subjects — driven end to end in one thread,
because :class:`InProcessMessageBus` delivers inline. Neither side is stubbed: the real
:class:`Gateway` talks to the real :class:`Shard`, which drives the real ``Lobby``.

The spectator is not a footnote here. A room with a watcher in it is the case where every
part of the design has to be right at once: the shard must publish once rather than per
person, the gateway must follow the room once however many are in it, the watcher must see
what the players see, and the shard must still refuse a move from someone who has no seat.
"""

from kfchess.bus import subjects
from kfchess.bus.message_bus import InProcessMessageBus
from kfchess.gateway.app import Gateway
from kfchess.model.board import Board
from kfchess.model.color import Color
from kfchess.model.piece import Piece
from kfchess.model.piece_type import standard_piece_types
from kfchess.services.rooms import Rooms
from kfchess.server.shard import Shard
from kfchess.server.user_store import UserStore
from kfchess.shared.codes import RejectReason
from kfchess.shared.protocol import (
    CreateRoom,
    Disconnected,
    JoinRoom,
    Login,
    Move,
    MoveStarted,
    Play,
    Rejected,
    Settled,
    Seated,
    State,
    decode,
    encode,
)


def a_board():
    """A 3x3 board with a lone white rook at a1."""
    reg = standard_piece_types()
    return Board.from_grid([
        [None, None, None],
        [None, None, None],
        [Piece(reg.get("R"), Color.WHITE), None, None],
    ])


class Client:
    """A socket's worth of client: what it was sent, decoded."""

    def __init__(self, gateway):
        self.received = []
        self.conn_id = gateway.connect(lambda text: self.received.append(decode(text)))
        self._gateway = gateway

    def send(self, message):
        self._gateway.receive(self.conn_id, encode(message))

    def leave(self):
        self._gateway.disconnect(self.conn_id)

    def of_type(self, cls):
        return [message for message in self.received if isinstance(message, cls)]


def a_world(gateway_id="gw1"):
    """One bus, one gateway, one shard — the whole deployment, in one thread."""
    bus = InProcessMessageBus()
    gateway = Gateway(bus, gateway_id)
    shard = Shard(bus, a_board, UserStore(":memory:"))
    return bus, gateway, shard


def logged_in(gateway, name):
    client = Client(gateway)
    client.send(Login(name, "pw"))
    return client


# --- a game across the two processes -------------------------------------------

def test_two_players_are_matched_and_a_move_crosses_the_split():
    _, gateway, shard = a_world()
    white, black = logged_in(gateway, "Efrat"), logged_in(gateway, "Dan")

    white.send(Play())
    black.send(Play())
    assert white.of_type(Seated)[-1].color is Color.WHITE
    assert black.of_type(Seated)[-1].color is Color.BLACK

    white.send(Move("WRa1a3"))

    for client in (white, black):
        started = client.of_type(MoveStarted)
        assert started and started[-1].from_sq == "a1" and started[-1].to_sq == "a3"


def test_the_game_goes_on_ticking_and_the_arrival_reaches_both():
    _, gateway, shard = a_world()
    white, black = logged_in(gateway, "Efrat"), logged_in(gateway, "Dan")
    white.send(Play())
    black.send(Play())
    white.send(Move("WRa1a3"))

    shard.tick(2000)  # the two-cell move lands

    assert black.of_type(Settled)[-1].at_sq == "a3"


def test_a_move_from_a_client_with_no_seat_is_refused_across_the_split():
    _, gateway, _ = a_world()
    watcher = logged_in(gateway, "Sam")

    watcher.send(Move("WRa1a3"))

    assert watcher.of_type(Rejected)[-1] == Rejected(RejectReason.NOT_A_PLAYER)


# --- spectators -----------------------------------------------------------------

def open_room_with_a_spectator():
    """A private room: white, black, and one watcher, all through the gateway."""
    bus = InProcessMessageBus()
    gateway = Gateway(bus, "gw1")
    # A known room id, so the joiners have something to type.
    shard = Shard(bus, a_board, UserStore(":memory:"), Rooms(generate_id=lambda: "AAAAAA"))

    white = logged_in(gateway, "Efrat")
    white.send(CreateRoom())
    black = logged_in(gateway, "Dan")
    black.send(JoinRoom("AAAAAA"))
    watcher = logged_in(gateway, "Sam")
    watcher.send(JoinRoom("AAAAAA"))
    return bus, gateway, shard, white, black, watcher


def test_a_spectator_is_seated_without_a_colour_and_sees_the_board():
    _, _, _, _, _, watcher = open_room_with_a_spectator()

    assert watcher.of_type(Seated)[-1] == Seated(None, "AAAAAA")
    assert watcher.of_type(State) != []  # the whole board, straight to the newcomer


def test_a_spectator_sees_the_moves_the_players_make():
    _, _, shard, white, _, watcher = open_room_with_a_spectator()

    white.send(Move("WRa1a3"))
    shard.tick(2000)

    assert watcher.of_type(MoveStarted)[-1].to_sq == "a3"
    assert [settled.at_sq for settled in watcher.of_type(Settled)] == ["a3"]


def test_a_spectator_cannot_move_but_the_game_carries_on():
    _, _, _, white, _, watcher = open_room_with_a_spectator()

    watcher.send(Move("WRa1a3"))
    assert watcher.of_type(Rejected)[-1] == Rejected(RejectReason.NOT_A_PLAYER)

    white.send(Move("WRa1a3"))  # the same move from someone who may make it
    assert white.of_type(MoveStarted) != []


def test_the_room_is_published_once_however_many_are_in_it():
    """The property the whole split is for: three people, one message on the wire."""
    bus, _, _, white, _, _ = open_room_with_a_spectator()
    before = len(bus.sent_to(subjects.room_inbox("0")))

    white.send(Move("WRa1a3"))

    # One sound and one delta -- not one of each per person in the room.
    assert len(bus.sent_to(subjects.room_inbox("0"))) - before == 2


def test_a_spectator_leaving_does_not_disturb_the_game():
    _, _, shard, white, black, watcher = open_room_with_a_spectator()

    watcher.leave()
    white.send(Move("WRa1a3"))
    shard.tick(2000)

    assert black.of_type(MoveStarted) != []   # the players carry on
    assert watcher.of_type(MoveStarted) == []  # and the watcher hears no more


def test_a_player_leaving_starts_a_countdown_the_spectator_also_sees():
    _, _, _, _, black, watcher = open_room_with_a_spectator()

    black.leave()

    # The countdown is the room's news, not a private message to the opponent.
    assert watcher.of_type(Disconnected)[-1].color is Color.BLACK


# --- two gateways ---------------------------------------------------------------

def test_a_second_gateway_serves_the_same_room_without_knowing_the_first():
    bus = InProcessMessageBus()
    here, there = Gateway(bus, "gw1"), Gateway(bus, "gw2")
    shard = Shard(bus, a_board, UserStore(":memory:"), Rooms(generate_id=lambda: "AAAAAA"))

    white = logged_in(here, "Efrat")
    white.send(CreateRoom())
    black = logged_in(there, "Dan")     # the other player is on the other gateway
    black.send(JoinRoom("AAAAAA"))

    white.send(Move("WRa1a3"))
    shard.tick(2000)

    assert black.of_type(MoveStarted)[-1].to_sq == "a3"
    assert black.of_type(Seated)[-1].color is Color.BLACK
