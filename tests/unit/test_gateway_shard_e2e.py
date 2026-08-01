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
from kfchess.config import MS_PER_CELL
from kfchess.bus.envelope import decode_to_client
from kfchess.bus.message_bus import InProcessMessageBus
from kfchess.gateway.app import Gateway
from kfchess.model.board import Board
from kfchess.model.color import Color
from kfchess.model.piece import Piece
from kfchess.model.piece_type import standard_piece_types
from kfchess.services.shared import SharedState
from kfchess.services.store import InMemoryKeyValueStore
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
    Resume,
    Settled,
    Seated,
    State,
    Welcome,
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
    shard = Shard(bus, a_board, UserStore(":memory:"), SharedState.on(generate_id=lambda: "AAAAAA"))

    white = logged_in(gateway, "Efrat")
    white.send(CreateRoom())
    black = logged_in(gateway, "Dan")
    black.send(JoinRoom("AAAAAA"))
    watcher = logged_in(gateway, "Sam")
    watcher.send(JoinRoom("AAAAAA"))
    return bus, gateway, shard, white, black, watcher


def test_a_spectator_is_seated_without_a_colour_and_sees_the_board():
    _, _, _, _, _, watcher = open_room_with_a_spectator()

    seated = watcher.of_type(Seated)[-1]
    assert (seated.color, seated.room_id) == (None, "AAAAAA")
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
    shard = Shard(bus, a_board, UserStore(":memory:"), SharedState.on(generate_id=lambda: "AAAAAA"))

    white = logged_in(here, "Efrat")
    white.send(CreateRoom())
    black = logged_in(there, "Dan")     # the other player is on the other gateway
    black.send(JoinRoom("AAAAAA"))

    white.send(Move("WRa1a3"))
    shard.tick(2000)

    assert black.of_type(MoveStarted)[-1].to_sq == "a3"
    assert black.of_type(Seated)[-1].color is Color.BLACK


# --- S3 exit criterion: the token is checked by the shard, not by the gateway ---

def test_a_wrong_seat_token_is_refused_across_the_bus():
    """The refusal comes back from the shard, through a gateway that read nothing.

    ``test_gateway_boundary`` is the other half of this: it forbids the gateway from
    importing the directory at all, so it *could* not check a token even if some later
    convenience wanted it to. This half shows the refusal still arrives.
    """
    bus, gateway, shard = a_world()
    white = logged_in(gateway, "Efrat")
    black = logged_in(gateway, "Dan")
    white.send(Play())
    black.send(Play())
    black.leave()  # her socket drops, mid-game

    impostor = Client(gateway)
    impostor.send(Resume("Dan", "not-the-token"))

    assert impostor.of_type(Rejected)[-1].reason is RejectReason.BAD_SEAT
    assert impostor.of_type(Seated) == []


def test_the_right_seat_token_gets_the_seat_back_across_the_bus():
    bus, gateway, shard = a_world()
    white = logged_in(gateway, "Efrat")
    black = logged_in(gateway, "Dan")
    white.send(Play())
    black.send(Play())
    token = black.of_type(Seated)[-1].seat_token
    black.leave()

    returner = Client(gateway)
    returner.send(Resume("Dan", token))

    assert returner.of_type(Welcome)[-1].color is Color.BLACK
    assert returner.of_type(State) != []  # and the board arrives on the new connection


# --- S4: two shards on one bus -------------------------------------------------

def two_shards():
    """One bus, one gateway, two shards — sharing accounts and shared state, as deployed."""
    bus = InProcessMessageBus()
    gateway = Gateway(bus, "gw1")
    users = UserStore(":memory:")
    store = InMemoryKeyValueStore()
    first = Shard(bus, a_board, users, SharedState.on(store, "sh1"))
    second = Shard(bus, a_board, users, SharedState.on(store, "sh2"))
    return bus, gateway, first, second


def owner_of(bus, conn_id):
    """Which shard claimed this connection, read off the wire."""
    claims = [
        decode_to_client(payload).claim
        for payload in bus.sent_to(subjects.connection(conn_id))
        if decode_to_client(payload).claim is not None
    ]
    return claims[-1] if claims else None


def test_exactly_one_shard_claims_each_connection():
    """Without the queue group both would, and both would run a copy of her game."""
    bus, gateway, _, _ = two_shards()

    client = Client(gateway)

    claims = [
        decode_to_client(payload).claim
        for payload in bus.sent_to(subjects.connection(client.conn_id))
    ]
    assert [claim for claim in claims if claim is not None] == [owner_of(bus, client.conn_id)]


def test_two_connections_are_shared_between_the_shards():
    bus, gateway, _, _ = two_shards()

    first, second = Client(gateway), Client(gateway)

    assert {owner_of(bus, first.conn_id), owner_of(bus, second.conn_id)} == {"sh1", "sh2"}


def test_everything_a_client_says_goes_to_the_shard_that_claimed_her():
    """The stickiness the whole design rests on: her login and her Play meet one shard."""
    bus, gateway, _, _ = two_shards()
    client = Client(gateway)
    mine = owner_of(bus, client.conn_id)
    theirs = "sh2" if mine == "sh1" else "sh1"

    client.send(Login("Efrat", "pw"))
    client.send(Play())

    assert len(bus.sent_to(subjects.shard_cmd(mine))) == 2
    assert bus.sent_to(subjects.shard_cmd(theirs)) == []


def test_a_player_seated_by_one_shard_is_unknown_to_the_other():
    """Two shards, two lobbies, no shared client list — and none needed."""
    bus, gateway, _, _ = two_shards()
    client = Client(gateway)

    client.send(Login("Efrat", "pw"))

    assert client.of_type(Welcome)[-1].rating == 1200  # answered exactly once
    assert len(client.of_type(Welcome)) == 1


def sought(gateway, name):
    """A logged-in client who has pressed Play."""
    client = logged_in(gateway, name)
    client.send(Play())
    return client


def test_two_players_claimed_by_different_shards_are_seated_in_one_game():
    """The stage in one test: the queue pairs them, one shard runs it, both are seated."""
    bus, gateway, _, _ = two_shards()

    white = sought(gateway, "Efrat")   # claimed by one shard, now waiting
    black = sought(gateway, "Dan")     # claimed by the other, and matched with her

    assert white.of_type(Seated)[-1].color is Color.WHITE
    assert black.of_type(Seated)[-1].color is Color.BLACK


def test_the_game_they_are_seated_in_is_the_same_game():
    bus, gateway, _, _ = two_shards()
    white = sought(gateway, "Efrat")
    black = sought(gateway, "Dan")

    white.send(Move("WRa1a3"))

    assert [m.to_sq for m in black.of_type(MoveStarted)] == ["a3"]


def test_both_connections_end_up_owned_by_the_shard_running_the_game():
    """Her moves have to arrive where her game is, so the seat moves the connection."""
    bus, gateway, _, _ = two_shards()
    white = sought(gateway, "Efrat")
    black = sought(gateway, "Dan")

    assert owner_of(bus, white.conn_id) == owner_of(bus, black.conn_id)


def test_the_shard_that_let_go_keeps_nothing_behind():
    """A shard nobody told would hold a client record for a socket it never hears again."""
    bus, gateway, first, second = two_shards()
    white = sought(gateway, "Efrat")
    sought(gateway, "Dan")  # the match, and the handover with it
    owner = owner_of(bus, white.conn_id)
    other = second if owner == "sh1" else first

    assert other.clients == 0


def test_a_game_handed_over_still_ends_and_still_pays_out():
    """Nothing about the game changed because it moved: it is the same lobby running it."""
    bus, gateway, first, second = two_shards()
    white = sought(gateway, "Efrat")
    black = sought(gateway, "Dan")

    white.send(Move("WRa1a3"))
    for shard in (first, second):
        shard.tick(2 * MS_PER_CELL)

    assert [m.at_sq for m in black.of_type(Settled)] == ["a3"]
