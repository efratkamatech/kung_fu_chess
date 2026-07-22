"""Lobby: the one hub that runs many games and routes each client to the right one.

Where the old single-game ``GameServer`` owned exactly one :class:`GameSession`, the
lobby owns *many*. A client's life now has three states (see the state diagram we drew):

- **connected** — the socket is open but nothing else is known.
- **in the lobby** — logged in (a :class:`Welcome` was sent), but not seated in any game.
- **in a game** — placed in a :class:`GameSession` with a colour, by matchmaking today
  (rooms in M6 will be a second door into the same place).

Every inbound message is dispatched by the client's state, and every broadcast is
*per game*: a snapshot goes only to the clients sharing that ``session_id``, so two
games running at once never see each other. Timeouts (a lone matchmaking search) ride
the same ``tick(dt_ms)`` that advances the games, so there is no real clock here and
every branch is unit-tested with fake ``send`` callbacks — no sockets at all. The async
:func:`kfchess.server.game_server.serve` is the only part that touches real WebSockets.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional

from kfchess.model.board import Board
from kfchess.model.color import Color
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
from kfchess.server.matchmaker import Matchmaker
from kfchess.server.session import GameSession
from kfchess.server.user_store import UserStore

Send = Callable[[str], None]      # how the lobby pushes one wire string to one client
NewBoard = Callable[[], Board]    # makes a fresh starting board for each new game


@dataclass
class _Client:
    """Everything the lobby tracks about one connected client, updated as it plays."""

    send: Send
    username: Optional[str] = None      # set on a successful login
    rating: Optional[int] = None        # the account's ELO, from the login
    session_id: Optional[int] = None    # which game it is in; None means "in the lobby"
    color: Optional[Color] = None       # its seat in that game; None means spectator


@dataclass
class _LiveGame:
    """One running game plus whether its result has already been rated (once)."""

    session: GameSession
    recorded: bool = False


class Lobby:
    """The synchronous hub: log players in, matchmake them, and route their moves."""

    def __init__(self, new_board: NewBoard, users: UserStore) -> None:
        self._new_board = new_board
        self._users = users
        self._matchmaker = Matchmaker()
        self._clients: dict[int, _Client] = {}
        self._games: dict[int, _LiveGame] = {}
        self._next_client_id = 0
        self._next_game_id = 0

    # --- connection lifecycle ------------------------------------------------

    def connect(self, send: Send) -> int:
        """Register a new client (in the "connected" state) and return its id.

        Nothing is sent yet: there is no game to show until the player logs in and is
        seated. The id is used by :meth:`receive` and :meth:`disconnect`.
        """
        client_id = self._next_client_id
        self._next_client_id += 1
        self._clients[client_id] = _Client(send)
        return client_id

    def disconnect(self, client_id: int) -> None:
        """Forget a client that has left; if it was mid-game, start its resign countdown.

        A player who drops out of a game is not removed from it — the game is kept so the
        opponent keeps seeing the board with a countdown, and wins by default if the
        player does not come back before it runs out (auto-resign, applied in :meth:`tick`).
        """
        self._matchmaker.cancel(client_id)
        client = self._clients.get(client_id)
        if client is not None and client.session_id is not None and client.color is not None:
            self._games[client.session_id].session.mark_disconnected(client.color)
        self._clients.pop(client_id, None)

    # --- inbound messages ----------------------------------------------------

    def receive(self, client_id: int, text: str) -> None:
        """Handle one wire message, dispatched by type. Unknown ones are ignored."""
        if client_id not in self._clients:
            return  # a message from a client we do not know (e.g. already disconnected)
        try:
            message = decode(text)
        except ValueError:
            return  # not valid JSON, or an unknown message type
        if isinstance(message, Login):
            self._on_login(client_id, message.username, message.password)
        elif isinstance(message, Play):
            self._on_play(client_id)
        elif isinstance(message, Move):
            self._on_move(client_id, message.cmd)
        # anything else is not something a client sends -- drop it

    def _on_login(self, client_id: int, username: str, password: str) -> None:
        """Authenticate and, on success, move the client into the lobby.

        Login no longer seats anyone: it registers a first-seen username or verifies a
        returning one, records the name and rating, and sends a :class:`Welcome` with no
        colour ("you're in the lobby"). A seat comes later, from matchmaking. A bad
        password is refused so the same connection can try again.
        """
        rating = self._users.register_or_login(username, password)
        if rating is None:
            self._send(client_id, Rejected("bad_password"))
            return
        client = self._clients[client_id]
        client.username = username
        client.rating = rating
        self._send(client_id, Welcome(client.color, rating))

    def _on_play(self, client_id: int) -> None:
        """Handle a "Play" request: try to matchmake this client, else queue it.

        Ignored (idempotently) if the client has not logged in, is already in a game, or
        is already searching. A pairing starts a new game at once; otherwise the client
        waits and will either be matched by a later seeker or time out in :meth:`tick`.
        """
        client = self._clients[client_id]
        if client.username is None or client.rating is None:
            return  # must be logged in to seek a game
        if client.session_id is not None:
            return  # already playing
        if self._matchmaker.is_waiting(client_id):
            return  # already searching
        match = self._matchmaker.seek(client_id, client.rating)
        if match is not None:
            self._start_game(match.white, match.black)

    def _start_game(self, white_id: int, black_id: int) -> None:
        """Create a game, seat the two matched clients, and show them the board."""
        game_id = self._next_game_id
        self._next_game_id += 1
        game = _LiveGame(GameSession(self._new_board()))
        self._games[game_id] = game
        for client_id in (white_id, black_id):
            client = self._clients[client_id]
            color = game.session.assign_color()  # WHITE first, then BLACK
            client.session_id = game_id
            client.color = color
            game.session.set_name(color, client.username)
            game.session.set_rating(color, client.rating)
            self._send(client_id, Seated(color))
        self._broadcast_events(game_id)  # the queued "game started" sound
        self._broadcast_state(game_id)

    def _on_move(self, client_id: int, cmd: str) -> None:
        """Apply a move to the sender's game, or refuse it, telling only that game."""
        client = self._clients[client_id]
        if client.session_id is None:
            self._send(client_id, Rejected("not_a_player"))
            return
        game = self._games[client.session_id]
        reason = game.session.apply_command(client.color, cmd)
        if reason is not None:
            self._send(client_id, Rejected(reason))
            return
        self._maybe_record_result(client.session_id)
        self._broadcast_events(client.session_id)
        self._broadcast_state(client.session_id)

    # --- time ----------------------------------------------------------------

    def tick(self, dt_ms: int) -> None:
        """Advance every game and the matchmaking clock by ``dt_ms``.

        Each game resolves its arrivals, records a finished result once, and broadcasts
        to its own members. Any matchmaking search that has now waited too long is told
        no opponent was found (and has already been dropped from the queue).
        """
        for game_id, game in self._games.items():
            game.session.tick(dt_ms)
            self._maybe_record_result(game_id)
            self._broadcast_events(game_id)
            self._broadcast_state(game_id)
        for client_id in self._matchmaker.tick(dt_ms):
            self._send(client_id, Notice("no_opponent"))

    def _maybe_record_result(self, game_id: int) -> None:
        """When a game has just ended, apply the ELO update once and show the new ratings.

        A matchmade game always has two known players, so there is no "unrated" case
        here (rooms bring that back in M6); this simply reads the winner off a snapshot,
        persists both ratings, and writes them back for the next broadcast.
        """
        game = self._games[game_id]
        if game.recorded:
            return
        snapshot = game.session.snapshot()
        if snapshot.winner is None:
            return
        game.recorded = True
        winner, loser = snapshot.winner, snapshot.winner.opponent
        self._users.record_win(snapshot.names[winner], snapshot.names[loser])
        game.session.set_rating(winner, self._users.get_rating(snapshot.names[winner]))
        game.session.set_rating(loser, self._users.get_rating(snapshot.names[loser]))

    # --- broadcasting --------------------------------------------------------

    def _members(self, game_id: int) -> List[_Client]:
        """The clients currently seated in (or watching) one game."""
        return [c for c in self._clients.values() if c.session_id == game_id]

    def _broadcast_state(self, game_id: int) -> None:
        """Send the game's current snapshot to each of its members."""
        text = encode(State(self._games[game_id].session.snapshot()))
        for client in self._members(game_id):
            client.send(text)

    def _broadcast_events(self, game_id: int) -> None:
        """Send each queued sound-kind event to the game's members, before its state.

        With no members left (both players gone), the queue is left intact rather than
        drained into the void — mirroring the old server's care with the game-start
        sound — though in practice a live game always has at least one member.
        """
        members = self._members(game_id)
        if not members:
            return
        for kind in self._games[game_id].session.drain_events():
            text = encode(Event(kind))
            for client in members:
                client.send(text)

    def _send(self, client_id: int, message) -> None:
        """Encode and push one message to a single (known) client."""
        self._clients[client_id].send(encode(message))
