"""The measurements are wired to the things they claim to measure.

Coverage would be satisfied by importing the module, which would prove nothing: a metric
declared and never touched is worse than no metric, because a graph of it reads as "this
never happens" rather than as "nobody counted".

Everything here is asserted as a *delta*, because the registry is one per process and
these tests share it with every other test in the run. Absolute values would depend on
the order pytest happened to pick.
"""

from kfchess.config import MS_PER_CELL
from kfchess.model.board import Board
from kfchess.model.color import Color
from kfchess.model.piece import Piece
from kfchess.model.piece_type import standard_piece_types
from kfchess.obs.measures import (
    ACTIVE_GAMES,
    BYTES_OUT,
    CONNECTIONS,
    GAME_TICK_US,
    MATCHES,
    MOVE_HANDLING_MS,
)
from kfchess.server.solo import build
from kfchess.server.user_store import UserStore
from kfchess.shared.protocol import Login, Move, Play, decode, encode


def a_board():
    reg = standard_piece_types()
    return Board.from_grid([
        [None, None, None],
        [None, None, None],
        [Piece(reg.get("R"), Color.WHITE), None, None],
    ])


class Client:
    def __init__(self, gateway):
        self.received = []
        self.conn_id = gateway.connect(lambda text: self.received.append(decode(text)))
        self._gateway = gateway

    def send(self, message):
        self._gateway.receive(self.conn_id, encode(message))


def a_game():
    """The whole server in one process, with two players matched into a game."""
    gateway, shard = build(a_board, UserStore(":memory:"))
    white, black = Client(gateway), Client(gateway)
    for client, name in ((white, "Efrat"), (black, "Dan")):
        client.send(Login(name, "pw"))
        client.send(Play())
    return gateway, shard, white


def test_matching_two_players_counts_a_match():
    before = MATCHES.value

    a_game()

    assert MATCHES.value - before == 1


def test_a_running_game_is_counted_while_it_runs():
    _, shard, _ = a_game()

    shard.tick(1)

    assert ACTIVE_GAMES.value == 1


def test_ticking_a_game_times_it():
    _, shard, _ = a_game()
    before = GAME_TICK_US.count

    shard.tick(MS_PER_CELL)

    assert GAME_TICK_US.count - before == 1


def test_handling_a_move_times_it():
    _, _, white = a_game()
    before = MOVE_HANDLING_MS.count

    white.send(Move("WRa1a3"))

    assert MOVE_HANDLING_MS.count - before == 1


def test_a_refused_move_is_not_counted_as_handled():
    """It is a refusal, not a move. Averaging the two would flatter the number."""
    _, _, white = a_game()
    before = MOVE_HANDLING_MS.count

    white.send(Move("WRa1z9"))  # off the board

    assert MOVE_HANDLING_MS.count == before


def test_holding_a_socket_is_counted_and_letting_go_is_too():
    gateway, _ = build(a_board, UserStore(":memory:"))

    first = Client(gateway)
    Client(gateway)
    assert CONNECTIONS.value == 2

    gateway.disconnect(first.conn_id)
    assert CONNECTIONS.value == 1


def test_everything_written_towards_a_player_is_weighed():
    """Counted at the gateway, per socket: that is where one message becomes many."""
    gateway, shard = build(a_board, UserStore(":memory:"))
    client = Client(gateway)
    before = BYTES_OUT.value

    client.send(Login("Efrat", "pw"))  # answered with a Welcome

    written = BYTES_OUT.value - before
    assert written == sum(len(encode(message)) for message in client.received)
    assert written > 0


def test_a_rooms_broadcast_is_weighed_once_per_person_in_it():
    """One message on the wire, two players hearing it -- and two players' worth of bytes."""
    gateway, shard = build(a_board, UserStore(":memory:"))
    white, black = Client(gateway), Client(gateway)
    for client, name in ((white, "Efrat"), (black, "Dan")):
        client.send(Login(name, "pw"))
        client.send(Play())
    before = BYTES_OUT.value

    white.send(Move("WRa1a3"))

    # The delta went to both of them, so both copies are counted.
    assert BYTES_OUT.value - before >= 2 * len(encode(white.received[-1]))
