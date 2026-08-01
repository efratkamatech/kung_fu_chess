"""The solo server: two players, one process, nothing installed.

``test_gateway_shard_e2e`` proves the split deployment works by wiring a gateway to a
shard by hand. This proves the *other* deployment works — and that it is the same code,
which is the claim that actually matters. If the local game were a second implementation
it would drift, quietly, and the drift would only ever be found by the person who tried
to play at home.

So nothing here stubs anything. ``solo.build`` returns the real gateway and the real
shard, and a whole game is played through them: log in, get matched, move a rook, watch
it arrive. What it does *not* have is a NATS server, a Redis, a database server or a
container — which is the entire point.
"""

from kfchess.config import MS_PER_CELL
from kfchess.model.board import Board
from kfchess.model.color import Color
from kfchess.model.piece import Piece
from kfchess.model.piece_type import standard_piece_types
from kfchess.server.solo import build
from kfchess.server.user_store import UserStore
from kfchess.shared.protocol import (
    Login,
    Move,
    MoveStarted,
    Play,
    Seated,
    Settled,
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

    def of_type(self, cls):
        return [message for message in self.received if isinstance(message, cls)]


def a_game():
    """The whole server in one process, with two players matched into a game."""
    gateway, shard = build(a_board, UserStore(":memory:"))
    white, black = Client(gateway), Client(gateway)
    for client, name in ((white, "Efrat"), (black, "Dan")):
        client.send(Login(name, "pw"))
        client.send(Play())
    return shard, white, black


def test_two_players_are_matched_with_no_infrastructure_at_all():
    _, white, black = a_game()

    assert white.of_type(Seated)[-1].color is Color.WHITE
    assert black.of_type(Seated)[-1].color is Color.BLACK
    assert white.of_type(State) != []  # and each was shown the board


def test_a_move_reaches_the_other_player_through_the_in_process_bus():
    """The room broadcast, delivered by a function call instead of by NATS."""
    _, white, black = a_game()

    white.send(Move("WRa1a3"))

    assert [(m.token, m.to_sq) for m in black.of_type(MoveStarted)] == [("wR", "a3")]


def test_the_clock_still_runs_the_game_forward():
    shard, white, black = a_game()
    white.send(Move("WRa1a3"))

    shard.tick(2 * MS_PER_CELL)  # long enough for the rook to arrive

    assert [m.at_sq for m in black.of_type(Settled)] == ["a3"]


def test_a_seat_is_written_down_even_with_the_store_in_this_process():
    """The directory is not skipped locally — the same lookup answers, from a dict."""
    _, white, _ = a_game()

    assert white.of_type(Seated)[-1].seat_token != ""
