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
:class:`kfchess.server.shard.Shard` is the only part that touches the bus, and the
gateway on its far side is the only part that touches a socket.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from time import perf_counter
from hmac import compare_digest
from typing import Callable, List, Optional, Tuple

from kfchess.bus import envelope, subjects
from kfchess.config import SNAPSHOT_RESYNC_MS
from kfchess.model.board import Board
from kfchess.model.color import Color
from kfchess.obs.measures import GAME_TICK_US, MATCHES, MOVE_HANDLING_MS
from kfchess.shared.codes import NoticeReason, RejectReason
from kfchess.shared.protocol import (
    CreateRoom,
    JoinRoom,
    Login,
    Move,
    Notice,
    Play,
    Rejected,
    Resume,
    Seated,
    State,
    Welcome,
    decode,
    encode,
)
from kfchess.server.session import GameSession
from kfchess.services.directory import Seat
from kfchess.services.rooms import RoomIdUnavailable
from kfchess.services.shared import SharedState
from kfchess.server.user_store import UserStore

Send = Callable[[str], None]      # how the lobby pushes one wire string to one client
NewBoard = Callable[[], Board]    # makes a fresh starting board for each new game
ToRoom = Callable[[str, str], None]  # how it addresses a whole room: (subject, text)

_log = logging.getLogger(__name__)  # activity trail; silent until configure_logging runs


@dataclass
class _Client:
    """Everything the lobby tracks about one connected client, updated as it plays."""

    send: Send
    # How the world outside this process names this client's socket. Opaque here — the
    # lobby never reads it — but it is the only thing another shard could use to reach
    # her, so it travels with any match she is part of.
    address: str = ""
    username: Optional[str] = None      # set on a successful login
    rating: Optional[int] = None        # the account's ELO, from the login
    session_id: Optional[int] = None    # which game it is in; None means "in the lobby"
    color: Optional[Color] = None       # its seat in that game; None means spectator


@dataclass
class _LiveGame:
    """One running game, its rated-once flag, and how long since its last full snapshot.

    The resync clock is per game rather than global so that a game started a moment ago
    is not resynced immediately along with one that has been running for ten seconds.
    """

    session: GameSession
    recorded: bool = False
    since_resync_ms: int = 0


class Lobby:
    """The synchronous hub: log players in, matchmake them, and route their moves."""

    def __init__(
        self,
        new_board: NewBoard,
        users: UserStore,
        shared: Optional[SharedState] = None,
        to_room: Optional[ToRoom] = None,
        to_shard: Optional[ToRoom] = None,
    ) -> None:
        self._new_board = new_board
        self._users = users
        # Where a whole room's traffic goes. Two sinks, because they are two different
        # destinations: `send` on a _Client answers one person, and this one addresses a
        # *place* — everyone in a game, players and spectators, without naming any of
        # them. Injected, so the same hub runs as one process (the default below) or as
        # a shard publishing to a subject.
        self._to_room = to_room if to_room is not None else self._send_to_members
        # How this lobby reaches another shard. ``None`` means it is not wired to a bus
        # at all -- a lobby driven directly by a test -- and such a lobby can only seat
        # players it is already holding.
        self._to_shard = to_shard
        # Injected, for the same reason as the room sink above: the default keeps the
        # queue and the room ids in this process, and one built on a shared store keeps
        # them where every other shard can see them. The lobby cannot tell which it got.
        shared = shared if shared is not None else SharedState.on()
        self._matchmaker = shared.matchmaker
        self._rooms = shared.rooms
        self._directory = shared.directory
        self._allocator = shared.allocator
        self._shard_id = shared.shard_id
        self._clients: dict[int, _Client] = {}
        # Who, of the players waiting in that shared queue, is one of mine. The queue
        # deals in usernames, because a client number means something only in the process
        # that issued it; this is the way back from the one to the other.
        self._seeking: dict[str, int] = {}
        self._games: dict[int, _LiveGame] = {}
        # Who is in each game, kept up to date as clients are seated and leave. It used
        # to be recomputed by scanning every client on the server -- twice per game, per
        # tick -- which is fine for two games and quadratic for ten thousand.
        self._members_by_game: dict[int, set[int]] = {}
        self._next_client_id = 0
        self._next_game_id = 0

    # --- connection lifecycle ------------------------------------------------

    def connect(self, send: Send, address: str = "") -> int:
        """Register a new client (in the "connected" state) and return its id.

        Nothing is sent yet: there is no game to show until the player logs in and is
        seated. The id is used by :meth:`receive` and :meth:`disconnect`; ``address`` is
        how anything outside this process would name the same client.
        """
        client_id = self._next_client_id
        self._next_client_id += 1
        self._clients[client_id] = _Client(send, address)
        _log.info("client %d connected", client_id)
        return client_id

    def disconnect(self, client_id: int) -> None:
        """Forget a client that has left; if it was mid-game, start its resign countdown.

        A player who drops out of a game is not removed from it — the game is kept so the
        opponent keeps seeing the board with a countdown, and wins by default if the
        player does not come back before it runs out (auto-resign, applied in :meth:`tick`).
        """
        client = self._clients.get(client_id)
        if client is None:
            return  # one we never knew, or have already forgotten
        self._stop_seeking(client)
        game_id = client.session_id
        if game_id is not None and client.color is not None:
            self._games[game_id].session.mark_disconnected(client.color)
        self._clients.pop(client_id, None)
        _log.info("client %d disconnected", client_id)
        if game_id is not None:
            self._members_by_game[game_id].discard(client_id)
            self._broadcast(game_id)  # tell the rest their opponent has dropped
            self._discard_if_empty(game_id)

    def _discard_if_empty(self, game_id: int) -> None:
        """Drop a game (and its room) once its last member has left, freeing its memory.

        Only empty games are removed, so no still-connected client is ever left pointing
        at a game that no longer exists. A game kept alive for a disconnect countdown
        (its opponent is still watching) is not empty, so it survives until they leave too.
        """
        if not self._members_by_game[game_id]:
            session = self._games[game_id].session
            for color in Color:
                name = session.name_of(color)
                if name is not None:
                    # Nobody is coming back to this: the last person in it has left. The
                    # entry would expire on its own -- that is what covers a shard that
                    # crashes -- but a player whose game just ended should not be sent
                    # back into it on her next login.
                    self._directory.leave(name)
            del self._games[game_id]
            del self._members_by_game[game_id]
            self._rooms.remove_game(game_id)

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
        elif isinstance(message, Resume):
            self._on_resume(client_id, message.username, message.seat_token)
        elif isinstance(message, Play):
            self._on_play(client_id)
        elif isinstance(message, CreateRoom):
            self._on_create_room(client_id)
        elif isinstance(message, JoinRoom):
            self._on_join_room(client_id, message.room_id)
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
            _log.info("client %d login refused for %r", client_id, username)
            self._send(client_id, Rejected(RejectReason.BAD_PASSWORD))
            return
        client = self._clients[client_id]
        client.username = username
        client.rating = rating
        _log.info("client %d logged in as %r (rating %d)", client_id, username, rating)
        seat = self._directory.seat_of(username)
        target = None if seat is None else self._seat_here(seat)
        if target is not None:
            self._reconnect(client_id, target, seat.seat_token)
            return
        self._send(client_id, Welcome(client.color, rating))

    def _on_resume(self, client_id: int, username: str, seat_token: str) -> None:
        """Put a player back in a seat she can prove is hers, without a password.

        The cheap way back. A password costs a hundred thousand hash rounds to check,
        and a reconnect happens on a bad network — which is to say, often, and in bursts.
        A token costs one lookup.

        **This shard is what checks it**, not the gateway that relayed the message and
        not anything reading the directory on the client's behalf: this shard minted the
        token when it seated her, and it owns the room the seat is in. A refusal is
        deliberately one answer for every way it can fail — no such player, wrong token,
        game finished, seat somewhere else. Telling an unknown caller *which* of those it
        was would let them map the seats they do not hold.
        """
        seat = self._directory.seat_of(username)
        target = None if seat is None else self._seat_here(seat)
        if seat is None or target is None or not compare_digest(seat.seat_token, seat_token):
            _log.info("client %d could not resume %r's seat", client_id, username)
            self._send(client_id, Rejected(RejectReason.BAD_SEAT))
            return
        client = self._clients[client_id]
        client.username = username
        client.rating = self._users.get_rating(username)
        self._reconnect(client_id, target, seat.seat_token)

    def _seat_here(self, seat: Seat) -> Optional[Tuple[int, Color]]:
        """The live local game a directory seat points at, or ``None``.

        This replaced a walk over every game on the server asking each one whether the
        returning player was in it — fine for the two games a laptop runs, hopeless at
        the numbers this is sized for, and impossible once the seat is not even on the
        machine doing the asking. The directory answers in one lookup, from anywhere.

        ``None`` for three different situations, and they are all "not here": the seat is
        on another shard, the game has since been discarded, or it has *ended*. That last
        one matters — being put back into a finished game would be worse than useless,
        since a client with a seat is one the lobby will not matchmake, so she would be
        stranded in a game that is over with no way to start another.
        """
        if seat.shard_id != self._shard_id:
            return None
        game = self._games.get(int(seat.room_id))
        if game is None or game.session.is_over():
            return None
        return int(seat.room_id), seat.color

    def _reconnect(
        self, client_id: int, target: Tuple[int, Color], seat_token: str
    ) -> None:
        """Put a returning player back in their seat and cancel any resign countdown."""
        game_id, color = target
        client = self._clients[client_id]
        self._evict_previous_holder(client_id, game_id, color)
        client.color = color
        self._join(client_id, game_id)
        self._games[game_id].session.reconnect()
        _log.info("client %d reconnected to game %d as %s", client_id, game_id, color.value)
        # Colour set => skip the lobby. The token rides along because she may not have
        # one: a player who closed the window and started the client again has just
        # proved herself with a password, and this is how she gets the cheaper proof back.
        self._send(client_id, Welcome(color, client.rating, seat_token))
        # The board, addressed to the returner, for the same reason a newcomer gets one
        # (see _seat): the room's copy waits on a subscription this message is asking for.
        self._send(client_id, State(self._games[game_id].session.snapshot()))
        self._broadcast(game_id)      # the "countdown cancelled" delta, to everyone
        self._broadcast_state(game_id)  # and the whole board, for everyone else

    def _evict_previous_holder(self, client_id: int, game_id: int, color: Color) -> None:
        """Detach whoever was holding this seat before, so no two clients share it.

        Usually nobody: the player dropped and that is why she is back. But after a
        gateway dies, the connection it held is still on the books here — nothing told
        this side it was gone — and leaving it seated would give one seat two owners.
        """
        for other_id in list(self._members_by_game[game_id]):
            other = self._clients[other_id]
            if other_id != client_id and other.color is color:
                other.session_id = None
                other.color = None
                self._members_by_game[game_id].discard(other_id)
                _log.info("client %d displaced from game %d", other_id, game_id)

    def _on_play(self, client_id: int) -> None:
        """Handle a "Play" request: try to matchmake this client, else queue it.

        Ignored (idempotently) if the client has not logged in, is already in a game, or
        is already searching. A pairing starts a new game at once; otherwise the player
        joins the shared queue and waits for a later seeker to find her.

        **Nothing here times her out.** The queue is not swept — counting down every
        waiter's clock twenty times a second is the one cost that grows with the number
        of people waiting rather than the number playing — so a player who is not matched
        gives up on her own client's clock, and the entry she leaves behind is removed by
        the next search that trips over it.
        """
        client = self._clients[client_id]
        if client.username is None or client.rating is None:
            return  # must be logged in to seek a game
        if client.session_id is not None:
            return  # already playing
        if self._matchmaker.is_waiting(client.username):
            return  # already searching
        self._seeking[client.username] = client_id
        match = self._matchmaker.seek(
            client.username, client.rating, client.address, self._shard_id
        )
        if match is None:
            return
        self._place(match, self._seeking.pop(match.black))

    def _place(self, match, black_id: int) -> None:
        """Get this pair a game, wherever it has to run and whoever is holding them.

        The fast path is both players on this shard and this shard chosen to run it,
        which is every game in a single-process deployment and most of them in a large
        one. Otherwise the pair is handed to the shard the allocator picked, and both
        connections leave this lobby: whoever takes the game takes them with it.
        """
        white_id = self._seeking.pop(match.white, None)
        target = self._allocator.allocate() or self._shard_id
        if white_id is not None and target == self._shard_id:
            self._start_game(white_id, black_id)
            return
        if self._to_shard is None:
            # No bus, so nothing to hand to. She goes back in the queue rather than being
            # dropped: she pressed Play and is owed a game, and the next seeker who can
            # seat her will find her there.
            self._matchmaker.seek(
                match.white, match.white_rating, match.white_conn_id, match.white_shard_id
            )
            _log.info("cannot reach %r from here; left in the queue", match.white)
            return
        black = self._clients[black_id]
        _log.info("game for %r and %r handed to %s", match.white, match.black, target)
        self._to_shard(
            subjects.shard_start_game(target),
            envelope.encode(
                envelope.StartGame(
                    envelope.Seatee(match.white_conn_id, match.white, match.white_rating),
                    envelope.Seatee(black.address, match.black, match.black_rating),
                )
            ),
        )
        # And now whoever was holding them lets go -- including this shard, through the
        # same message rather than by reaching into itself, so a connection is forgotten
        # in exactly one place however far away it was being held. The shard now running
        # the game is skipped: it has just claimed them, and telling it to let go of what
        # it was told to take would undo the seating a line above.
        for shard_id, conn_id in (
            (match.white_shard_id, match.white_conn_id),
            (self._shard_id, black.address),
        ):
            if shard_id and shard_id != target:
                self._to_shard(
                    subjects.shard_cmd(shard_id),
                    envelope.encode(
                        envelope.ClientEvent(
                            envelope.ClientEventKind.RELEASED, conn_id
                        )
                    ),
                )

    def start_game(self, white: Tuple[int, str, int], black: Tuple[int, str, int]) -> None:
        """Run a game between two clients another shard matched, and seat them.

        The receiving end of :meth:`_place`. The names and ratings arrive with the
        request because this shard may never have spoken to either player — that is the
        whole point of being able to hand a game over — and going to the database for
        what the queue was already sorted by would be a round trip to learn what somebody
        else had just read.
        """
        for client_id, username, rating in (white, black):
            client = self._clients[client_id]
            client.username = username
            client.rating = rating
        self._start_game(white[0], black[0])

    def release(self, client_id: int) -> None:
        """Forget a client that now belongs to another shard.

        Not a disconnect: her socket is fine, and the shard taking her over is about to
        seat her. So there is no resign countdown, nothing is broadcast, and the game she
        is being seated in is not this shard's to know about.
        """
        self._stop_seeking(self._clients.pop(client_id))
        _log.info("client %d released", client_id)

    def _stop_seeking(self, client: _Client) -> None:
        """Take a client out of the shared queue, if she is in it and has a name to be in
        it under. A no-op for anyone who never pressed Play."""
        if client.username is not None:
            self._matchmaker.cancel(client.username)
            self._seeking.pop(client.username, None)

    def _start_game(self, white_id: int, black_id: int) -> None:
        """Create a game, seat the two matched clients, and show them the board."""
        MATCHES.inc()
        game_id = self._new_game()
        self._seat(white_id, game_id)  # first assign_color -> WHITE
        self._seat(black_id, game_id)  # second -> BLACK
        self._broadcast(game_id)       # the queued "game started" sound
        self._broadcast_state(game_id)

    def _on_create_room(self, client_id: int) -> None:
        """Open a new private room; the creator plays white and gets its shareable id.

        If no free id can be found, the empty game is dropped again and the player is
        told to try again — the one thing that must not happen is the server spinning on
        the attempt, since a single thread runs every game on it.
        """
        client = self._clients[client_id]
        if client.username is None or client.session_id is not None:
            return
        self._stop_seeking(client)  # opening a room ends any pending search
        game_id = self._new_game()
        try:
            room_id = self._rooms.create(game_id)
        except RoomIdUnavailable:
            _log.warning("client %d: no free room id, game %d dropped", client_id, game_id)
            self._discard_if_empty(game_id)  # nobody was seated in it yet
            self._send(client_id, Notice(NoticeReason.ROOM_UNAVAILABLE))
            return
        self._games[game_id].session.set_room_id(room_id)
        _log.info("client %d opened room %s (game %d)", client_id, room_id, game_id)
        self._seat(client_id, game_id, room_id)  # assign_color -> WHITE
        self._broadcast(game_id)
        self._broadcast_state(game_id)

    def _on_join_room(self, client_id: int, room_id: str) -> None:
        """Join an existing room: second joiner is black, the rest are spectators.

        The room may not be here. Room ids are claimed where every shard can see the
        claim, so a player can type one into a client that happens to be talking to a
        shard which has never heard of it — and the answer is to send her where it is,
        not to tell her it does not exist.
        """
        client = self._clients[client_id]
        if client.username is None or client.session_id is not None:
            return
        self._stop_seeking(client)
        game_id = self._rooms.game_for(room_id)
        if game_id is not None:
            self._admit(client_id, game_id, room_id)
            return
        elsewhere = self._rooms.shard_of(room_id)
        if elsewhere is None or elsewhere == self._shard_id or self._to_shard is None:
            # No such room anywhere; or a claim outliving the game it was for; or this
            # lobby has no way to reach another shard. All three are the same answer.
            _log.info("client %d tried to join unknown room %s", client_id, room_id)
            self._send(client_id, Notice(NoticeReason.NO_SUCH_ROOM))
            return
        _log.info("client %d sent to room %s on %s", client_id, room_id, elsewhere)
        self._to_shard(
            subjects.shard_join_game(elsewhere),
            envelope.encode(
                envelope.JoinGame(
                    envelope.Seatee(client.address, client.username, client.rating),
                    room_id,
                )
            ),
        )
        self.release(client_id)

    def join_game(self, client_id: int, username: str, rating: int, room_id: str) -> None:
        """Admit somebody another shard sent here, into a room this one is running.

        The receiving end of the handover above, and the same method the local path takes
        once the two have converged: whether she was already talking to this shard or has
        just been redirected to it makes no difference to the seat she gets.
        """
        client = self._clients[client_id]
        client.username = username
        client.rating = rating
        game_id = self._rooms.game_for(room_id)
        if game_id is None:
            # It ended between her being sent here and arriving. Rare, and the honest
            # answer is the one she would have got a moment earlier.
            self._send(client_id, Notice(NoticeReason.NO_SUCH_ROOM))
            return
        self._admit(client_id, game_id, room_id)

    def _admit(self, client_id: int, game_id: int, room_id: str) -> None:
        """Seat a joiner in a room this shard runs, and show everyone the new arrival."""
        _log.info("client %d joined room %s (game %d)", client_id, room_id, game_id)
        self._seat(client_id, game_id, room_id)  # BLACK, then None (a spectator)
        self._broadcast(game_id)
        self._broadcast_state(game_id)

    def _new_game(self) -> int:
        """Create an empty game and return its id."""
        game_id = self._next_game_id
        self._next_game_id += 1
        self._games[game_id] = _LiveGame(GameSession(self._new_board()))
        self._members_by_game[game_id] = set()
        return game_id

    def _join(self, client_id: int, game_id: int) -> None:
        """Record that a client is now in a game — the one place membership is set."""
        self._clients[client_id].session_id = game_id
        self._members_by_game[game_id].add(client_id)

    def _seat(self, client_id: int, game_id: int, room_id: Optional[str] = None) -> None:
        """Place a client in a game: next free colour, or spectator when both seats are taken.

        Records the player's name and rating on the session (spectators have neither) and
        tells the client its colour with :class:`Seated` (carrying ``room_id`` for rooms).
        """
        game = self._games[game_id]
        client = self._clients[client_id]
        color = game.session.assign_color()  # WHITE, then BLACK, then None (spectator)
        self._join(client_id, game_id)
        client.color = color
        seat_token = ""
        if color is not None:
            game.session.set_name(color, client.username)
            game.session.set_rating(color, client.rating)
            # Written down where any shard can find it, so coming back is a lookup rather
            # than a search. A spectator gets no entry: she holds no seat, and nothing
            # would be waiting for her if she left.
            seat_token = self._directory.take_seat(
                client.username, str(game_id), self._shard_id, color
            ).seat_token
        role = "spectator" if color is None else color.value
        _log.info("client %d seated in game %d as %s", client_id, game_id, role)
        self._send(client_id, Seated(color, room_id, seat_token))
        # The board, straight to the newcomer, and not only to the room a moment later.
        # Running as a shard those are different journeys: the room's copy only arrives
        # once this client's gateway has finished subscribing to that room, and the
        # request to subscribe was the message just above. Addressed to the connection,
        # it cannot lose that race — which matters most for the person it is most likely
        # to affect, a spectator dropping into a game already in progress.
        self._send(client_id, State(game.session.snapshot()))

    @property
    def game_count(self) -> int:
        """How many games this lobby is running — what "load" means for a shard."""
        return len(self._games)

    def room_key(self, game_id: int) -> str:
        """How this game is addressed on the bus — unique across every shard.

        A game id is a counter in one process, so two shards each running their first
        game would both publish to ``room.0`` and every gateway would fan each game's
        moves out to the other's players. Carrying the shard's name makes the key as
        global as the subject it becomes. It is not the short code a player types for a
        private room: that one is chosen to be readable, and this one to be unique.
        """
        return f"{self._shard_id}-{game_id}"

    def game_of(self, client_id: int) -> Optional[int]:
        """Which game a client is in, or ``None`` for one still in the lobby or gone.

        The shard reads this to know when a connection has just been given a place, so it
        can tell that connection's gateway which room to follow. Membership is set in
        exactly one method (:meth:`_join`), so this cannot disagree with it.
        """
        client = self._clients.get(client_id)
        return client.session_id if client is not None else None

    def _on_move(self, client_id: int, cmd: str) -> None:
        """Apply a move to the sender's game, or refuse it, telling only that game."""
        started = perf_counter()
        client = self._clients[client_id]
        if client.session_id is None or client.color is None:
            self._send(client_id, Rejected(RejectReason.NOT_A_PLAYER))  # spectators cannot move
            return
        game = self._games[client.session_id]
        reason = game.session.apply_command(client.color, cmd)
        if reason is not None:
            _log.info("game %d: move %r refused (%s)", client.session_id, cmd, reason)
            self._send(client_id, Rejected(reason))
            return
        _log.info("game %d: %s played %s", client.session_id, client.color.value, cmd)
        self._maybe_record_result(client.session_id)
        self._broadcast(client.session_id)
        # The server's share of how quickly a move is felt: from the command arriving to
        # its delta being on the wire. The rest of what a player experiences is two
        # network hops, which this side cannot see and the load bot measures instead.
        MOVE_HANDLING_MS.observe((perf_counter() - started) * 1000)

    # --- time ----------------------------------------------------------------

    def tick(self, dt_ms: int) -> None:
        """Advance every game by ``dt_ms``.

        Each game resolves its arrivals, records a finished result once, and sends its
        own members whatever actually happened — usually nothing at all, since a tick
        where no piece arrives and no cooldown ends produces no messages.

        The people *waiting* for a game are no longer part of this. They used to be: each
        tick walked every waiter and advanced her clock, so the busiest moment — a queue
        with thousands in it and nobody yet playing — was also the most expensive one.
        Their patience is now measured on their own clients' clocks, which are exactly as
        numerous as the players themselves.
        """
        for game_id, game in self._games.items():
            # Timed around the session alone -- the engine advancing, the arbiter
            # resolving -- because that is the cost the "500 games to a shard" estimate
            # was built from. The broadcasting below it is charged to the network, not
            # to the game.
            started = perf_counter()
            game.session.tick(dt_ms)
            GAME_TICK_US.observe((perf_counter() - started) * 1_000_000)
            self._maybe_record_result(game_id)
            self._broadcast(game_id)
            self._resync_if_due(game_id, dt_ms)

    def next_event_delay_ms(self) -> Optional[int]:
        """The shortest wait before any game needs a tick, or ``None`` if all are idle.

        Only the games' *scheduled* work is in here. The resync clock and the matchmaking
        timeouts count elapsed time rather than name a moment, so they ride the caller's
        own interval instead — see :func:`kfchess.server.shard.next_sleep_s`, which
        is the one place the two are combined.
        """
        delays = [
            delay
            for delay in (
                game.session.next_event_delay_ms() for game in self._games.values()
            )
            if delay is not None
        ]
        return min(delays) if delays else None

    def _maybe_record_result(self, game_id: int) -> None:
        """When a game has just ended, apply the ELO update once and store both ratings.

        A matchmade game always has two known players; a room game may not (a lone
        creator can capture the unowned enemy king), so a game that ends without two
        known players is left unrated.

        The players have *already* been told their new ratings, in the ``GameOver`` delta
        the session computed the moment the game ended. This persists the same numbers:
        both sides run :func:`~kfchess.server.rating.updated_ratings` over the same pair,
        so what was shown and what was stored are the same arithmetic, and nobody waits
        on the database to see her result.
        """
        game = self._games[game_id]
        if game.recorded:
            return
        winner = game.session.winner
        if winner is None:
            return
        winner_name = game.session.name_of(winner)
        loser_name = game.session.name_of(winner.opponent)
        if winner_name is None or loser_name is None:
            return  # a seat was never filled; the game does not count
        game.recorded = True
        self._users.record_win(winner_name, loser_name)
        game.session.set_rating(winner, self._users.get_rating(winner_name))
        game.session.set_rating(winner.opponent, self._users.get_rating(loser_name))

    # --- broadcasting --------------------------------------------------------

    def _members(self, game_id: int) -> List[_Client]:
        """The clients currently seated in (or watching) one game."""
        return [self._clients[cid] for cid in self._members_by_game[game_id]]

    def _broadcast(self, game_id: int) -> None:
        """Send everything the game has queued — deltas and sounds — to its members.

        The common case is an empty queue: most ticks nothing happens, and a game with
        nothing to say now says nothing, where it used to send every client a fresh copy
        of the whole board.
        """
        for message in self._games[game_id].session.drain_deltas():
            self._to_room(subjects.room_delta(self.room_key(game_id)), encode(message))

    def _broadcast_state(self, game_id: int) -> None:
        """Send the game's full snapshot to the room.

        Reserved for the moments a whole picture is genuinely needed: someone was just
        seated (and everyone's view of who is playing changed), someone reconnected, or
        the periodic resync came due.
        """
        self._to_room(
            subjects.room_state(self.room_key(game_id)),
            encode(State(self._games[game_id].session.snapshot())),
        )

    def _send_to_members(self, subject: str, text: str) -> None:
        """The default room sink: hand the text to each member, in this process.

        What a single-process run does, and what every test of this class does. Running
        as a shard, the injected sink publishes once to ``subject`` instead and the
        fan-out happens at the gateways — which is the difference between a room's
        spectators costing the shard one message and costing it one message each.
        """
        for client in self._members(_game_of_key(subjects.room_of(subject))):
            client.send(text)

    def _resync_if_due(self, game_id: int, dt_ms: int) -> None:
        """Send a full snapshot every ``SNAPSHOT_RESYNC_MS``, to correct any drift.

        The clients rebuild the board from deltas, and arithmetic on two machines can
        part company — a dropped frame, a rounding difference. This is the floor under
        that: whatever a client believes, it is corrected within ten seconds.
        """
        game = self._games[game_id]
        game.since_resync_ms += dt_ms
        if game.since_resync_ms >= SNAPSHOT_RESYNC_MS:
            game.since_resync_ms = 0
            self._broadcast_state(game_id)

    def _send(self, client_id: int, message) -> None:
        """Encode and push one message to a single (known) client."""
        self._clients[client_id].send(encode(message))


def _game_of_key(room_key: str) -> int:
    """The game behind a room key — the inverse of :meth:`Lobby.room_key`.

    Only the single-process room sink needs this, because only it has to get back from a
    subject to an object in its own memory. A shard publishes and never looks back.
    """
    return int(room_key.rsplit("-", 1)[1])
