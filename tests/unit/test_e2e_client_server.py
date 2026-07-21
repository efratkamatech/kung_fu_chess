"""End-to-end (in-memory): a click on one client reaches the other via the server.

Wires the real GameServer hub to two real NetClients with an in-memory transport (each
client's send callback is the hub feeding it wire text back), then drives the whole
chain a real move takes: ClientController click -> command -> hub.receive -> session ->
broadcast -> NetClient.handle -> snapshot -> to_render_inputs. No sockets, so it is
deterministic, but every layer built in M2 is exercised together.
"""

from kfchess.client.controller import ClientController
from kfchess.client.net_client import NetClient
from kfchess.client.snapshot_view import to_render_inputs
from kfchess.model.board import Board
from kfchess.model.color import Color
from kfchess.model.piece import Piece
from kfchess.model.piece_type import standard_piece_types
from kfchess.model.position import Position
from kfchess.protocol import Login, Move, encode
from kfchess.server.game_server import GameServer
from kfchess.server.session import GameSession
from kfchess.server.user_store import UserStore


def wire_two_clients():
    """A hub over a lone white rook at a1, with white and black NetClients logged in."""
    reg = standard_piece_types()
    grid = [
        [None, None, None],
        [None, None, None],
        [Piece(reg.get("R"), Color.WHITE), None, None],
    ]
    hub = GameServer(GameSession(Board.from_grid(grid)), UserStore(":memory:"))
    white, black = NetClient(), NetClient()
    white_id = hub.connect(white.handle)  # the hub sends wire text straight to handle
    black_id = hub.connect(black.handle)
    hub.receive(white_id, encode(Login("Efrat", "pw")))  # first login -> white
    hub.receive(black_id, encode(Login("Dan", "pw")))    # second login -> black
    return hub, white, black, white_id, black_id


def test_a_move_by_white_reaches_black_through_the_server():
    hub, white, black, white_id, _ = wire_two_clients()

    # Each client learned its colour (from Welcome) and has a snapshot.
    assert white.color is Color.WHITE
    assert black.color is Color.BLACK
    assert white.latest() is not None and black.latest() is not None

    # White selects its rook at a1 and moves it to a3, via the client controller.
    controller = ClientController()
    snapshot = white.latest()
    assert controller.click(Position(2, 0), snapshot, white.color) is None  # select a1
    command = controller.click(Position(0, 0), snapshot, white.color)       # -> a3
    assert command == "WRa1a3"

    # Send it the real way: queue on the client, pull it off, deliver to the hub.
    white.queue_command(command)
    hub.receive(white_id, encode(Move(white.next_command())))

    # Server-authoritative: BOTH clients now see the rook in flight (the moving overlay).
    for client in (white, black):
        _, moving, _ = to_render_inputs(client.latest())
        assert len(moving) == 1
        assert moving[0].piece.piece_type.letter == "R"


def test_black_cannot_move_a_white_piece():
    hub, white, black, _, black_id = wire_two_clients()
    before = black.latest()

    # Black tries to move white's rook; the server refuses (not_your_piece) and the
    # game state does not change.
    hub.receive(black_id, encode(Move("BRa1a3")))

    assert black.take_rejection() == "not_your_piece"
    _, moving, _ = to_render_inputs(black.latest())
    assert moving == []                       # nothing started moving
    assert black.latest().phase == before.phase
