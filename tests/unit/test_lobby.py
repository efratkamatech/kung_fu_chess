"""Tests for the Lobby hub: login, matchmaking, routing, and per-game broadcast.

Driven with fake ``send`` callbacks (no sockets). Two clients with equal starting
ratings are always within the matchmaking window, so "log in and press Play on both"
is the standard way to get a running game.
"""

from kfchess.config import (
    MS_PER_CELL,
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
from kfchess.shared.protocol import (
    CreateRoom,
    Disconnected,
    Event,
    GameOver,
    JoinRoom,
    Login,
    Move,
    MoveStarted,
    Notice,
    Play,
    Reconnected,
    Rejected,
    Resume,
    Seated,
    State,
    Welcome,
    decode,
    encode,
)
from kfchess.server.lobby import Lobby
from kfchess.services.directory import PlayerDirectory
from kfchess.services.shared import SharedState
from kfchess.services.store import InMemoryKeyValueStore
from kfchess.server.user_store import UserStore
from kfchess.shared.codes import NoticeReason, RejectReason


class FakeClient:
    """Captures the messages the hub sends it (decoded from the wire)."""

    def __init__(self):
        self.received = []

    def send(self, text):
        self.received.append(decode(text))


def _rook_board():
    """A 3x3 board with a lone white rook at a1."""
    reg = standard_piece_types()
    grid = [
        [None, None, None],
        [None, None, None],
        [Piece(reg.get("R"), Color.WHITE), None, None],
    ]
    return Board.from_grid(grid)


def _king_board():
    """A 3x3 board: white rook at a1, black king at a3 (capturable)."""
    reg = standard_piece_types()
    grid = [
        [Piece(reg.get("K"), Color.BLACK), None, None],
        [None, None, None],
        [Piece(reg.get("R"), Color.WHITE), None, None],
    ]
    return Board.from_grid(grid)


def make_lobby(new_board=_rook_board):
    """A lobby that hands out ``new_board`` copies, on a fresh in-memory user store."""
    return Lobby(new_board, UserStore(":memory:"))


def login(hub, client_id, username="Efrat", password="pw"):
    hub.receive(client_id, encode(Login(username, password)))


def of_type(client, cls):
    return [m for m in client.received if isinstance(m, cls)]


def seat(client):
    """The last seat this client was given. Its token is random, so tests read fields."""
    return of_type(client, Seated)[-1]


def login_ready(hub, name, new_board=_rook_board):
    """Connect and log a client into the lobby; returns the client and its id."""
    client = FakeClient()
    cid = hub.connect(client.send)
    login(hub, cid, name)
    return client, cid


def seat_two(new_board=_rook_board):
    """Log in two clients and match them; returns the hub, both clients, and their ids."""
    hub = make_lobby(new_board)
    white, black = FakeClient(), FakeClient()
    wid, bid = hub.connect(white.send), hub.connect(black.send)
    login(hub, wid, "Efrat")
    login(hub, bid, "Dan")
    hub.receive(wid, encode(Play()))  # first: waits
    hub.receive(bid, encode(Play()))  # second: matches -> a game starts
    return hub, white, black, wid, bid


# --- connecting and logging in ------------------------------------------------

def test_connecting_sends_nothing_until_you_act():
    hub = make_lobby()
    client = FakeClient()
    hub.connect(client.send)
    assert client.received == []  # no board, no seat -- you are only "connected"


def test_login_welcomes_you_into_the_lobby_with_no_seat():
    hub = make_lobby()
    client = FakeClient()
    login(hub, hub.connect(client.send), "Efrat")
    assert of_type(client, Welcome)[-1] == Welcome(None, START_RATING)  # in the lobby


def test_a_wrong_password_is_refused_and_can_be_retried():
    hub = make_lobby()
    first = FakeClient()
    login(hub, hub.connect(first.send), "Efrat", "secret")  # registers Efrat/secret

    second = FakeClient()
    sid = hub.connect(second.send)
    login(hub, sid, "Efrat", "wrong")
    assert second.received[-1] == Rejected(RejectReason.BAD_PASSWORD)
    assert of_type(second, Welcome) == []

    login(hub, sid, "Efrat", "secret")  # retry, same connection
    assert of_type(second, Welcome)[-1] == Welcome(None, START_RATING)


# --- matchmaking --------------------------------------------------------------

def test_two_logged_in_players_who_press_play_are_matched():
    _, white, black, _, _ = seat_two()
    assert seat(white).color is Color.WHITE  # first to seek gets white
    assert seat(black).color is Color.BLACK


def test_a_matched_game_shows_both_players_the_board_and_start_sound():
    _, white, black, _, _ = seat_two()
    for client in (white, black):
        assert of_type(client, State)  # each got the starting snapshot
        assert of_type(client, Event) == [Event(SOUND_GAME_START)]


def test_the_matched_snapshot_carries_both_names_and_ratings():
    _, white, _, _, _ = seat_two()
    snapshot = of_type(white, State)[-1].snapshot
    assert snapshot.names == {Color.WHITE: "Efrat", Color.BLACK: "Dan"}
    assert snapshot.ratings == {Color.WHITE: START_RATING, Color.BLACK: START_RATING}


def test_a_lone_seeker_waits_and_is_not_seated():
    hub = make_lobby()
    client = FakeClient()
    cid = hub.connect(client.send)
    login(hub, cid, "Efrat")
    hub.receive(cid, encode(Play()))
    assert of_type(client, Seated) == []  # nobody to match with yet


def test_play_before_logging_in_is_ignored():
    hub = make_lobby()
    client = FakeClient()
    cid = hub.connect(client.send)
    hub.receive(cid, encode(Play()))  # no login first -- must not seat or crash
    assert of_type(client, Seated) == []


def test_pressing_play_twice_while_waiting_does_not_pair_you_with_yourself():
    hub = make_lobby()
    client = FakeClient()
    cid = hub.connect(client.send)
    login(hub, cid, "Efrat")
    hub.receive(cid, encode(Play()))
    hub.receive(cid, encode(Play()))  # second press: still just waiting
    assert of_type(client, Seated) == []


def test_pressing_play_again_while_already_in_a_game_is_ignored():
    hub, white, _, wid, _ = seat_two()
    before = len(white.received)
    hub.receive(wid, encode(Play()))  # already seated
    assert len(white.received) == before


def test_ticking_does_not_walk_the_people_who_are_waiting():
    """The queue is not swept. A lone seeker is left alone, however long the clock runs.

    This is a cost decision, not an oversight: sweeping is the one piece of per-tick work
    that grows with the number of people *waiting*, so the busiest moment a lobby has —
    thousands queued, nobody yet playing — used to be its most expensive. Giving up is
    now measured on the player's own client, and those are as numerous as the players.
    """
    from kfchess.config import MATCH_TIMEOUT_MS

    hub = make_lobby()
    client = FakeClient()
    cid = hub.connect(client.send)
    login(hub, cid, "Efrat")
    hub.receive(cid, encode(Play()))

    hub.tick(MATCH_TIMEOUT_MS * 10)

    assert of_type(client, Notice) == []
    assert of_type(client, Seated) == []


def test_a_player_who_gave_up_waiting_can_press_play_again():
    """What replaces the timeout: her client stops listening and offers the menu again.

    The server was never told she gave up — that is the point — so pressing Play must
    start a fresh search rather than be ignored as a search already in progress.
    """
    from kfchess.config import MATCH_TIMEOUT_MS

    now = [1_000_000]
    hub = Lobby(
        _rook_board, UserStore(":memory:"), SharedState.on(now_ms=lambda: now[0])
    )
    lone, lone_id = login_ready(hub, "Efrat")
    hub.receive(lone_id, encode(Play()))

    now[0] += MATCH_TIMEOUT_MS  # she waits it out and her client gives up
    hub.receive(lone_id, encode(Play()))  # ...and she tries again

    other, other_id = login_ready(hub, "Dan")
    hub.receive(other_id, encode(Play()))

    assert seat(lone).color is Color.WHITE  # the second search worked
    assert seat(other).color is Color.BLACK


# --- moves and routing --------------------------------------------------------

def test_a_move_before_being_in_a_game_is_rejected():
    hub = make_lobby()
    client = FakeClient()
    cid = hub.connect(client.send)
    login(hub, cid, "Efrat")  # in the lobby, but not in a game
    hub.receive(cid, encode(Move("WRa1a3")))
    assert client.received[-1] == Rejected(RejectReason.NOT_A_PLAYER)


def test_a_legal_move_broadcasts_its_sound_and_delta_to_both_players():
    """Two small messages describing the move — not a fresh copy of the board."""
    hub, white, black, wid, _ = seat_two()
    before = len(black.received)

    hub.receive(wid, encode(Move("WRa1a3")))

    assert black.received[-2:] == [
        Event(SOUND_MOVE),
        MoveStarted(0, "wR", "a1", "a3", 0, 2000),
    ]
    assert len(black.received) == before + 2


def test_an_illegal_move_is_rejected_to_the_sender_only():
    hub, white, black, wid, _ = seat_two()
    before_black = len(black.received)

    hub.receive(wid, encode(Move("WRa1b2")))  # rooks don't move diagonally

    assert white.received[-1] == Rejected("illegal_move")
    assert len(black.received) == before_black  # black saw nothing


def test_two_games_run_in_parallel_without_crossing_broadcasts():
    hub = make_lobby()
    a, b, c, d = FakeClient(), FakeClient(), FakeClient(), FakeClient()
    ids = [hub.connect(x.send) for x in (a, b, c, d)]
    for cid, name in zip(ids, ("A", "B", "C", "D")):
        login(hub, cid, name)
    hub.receive(ids[0], encode(Play()))
    hub.receive(ids[1], encode(Play()))  # A+B -> game one
    hub.receive(ids[2], encode(Play()))
    hub.receive(ids[3], encode(Play()))  # C+D -> game two

    before_c, before_d = len(c.received), len(d.received)
    hub.receive(ids[0], encode(Move("WRa1a3")))  # a move in game one

    assert isinstance(a.received[-1], MoveStarted)
    assert isinstance(b.received[-1], MoveStarted)
    assert len(c.received) == before_c  # game two saw nothing
    assert len(d.received) == before_d


def test_a_quiet_tick_sends_nobody_anything():
    """What S0 buys, measured at the hub: an idle game costs no traffic at all."""
    hub, white, black, _, _ = seat_two()
    before_white, before_black = len(white.received), len(black.received)

    hub.tick(50)

    assert len(white.received) == before_white
    assert len(black.received) == before_black


# --- housekeeping -------------------------------------------------------------

def test_garbage_and_non_client_messages_are_ignored():
    hub = make_lobby()
    client = FakeClient()
    cid = hub.connect(client.send)
    before = len(client.received)
    hub.receive(cid, "not json at all")            # unparseable
    hub.receive(cid, encode(Rejected(RejectReason.BAD_PASSWORD)))  # valid, not a client msg
    assert len(client.received) == before


def test_a_message_from_an_unknown_client_is_ignored_safely():
    hub = make_lobby()
    hub.receive(999, encode(Move("WRa1a3")))  # no such client id -- must not raise


def test_disconnecting_a_client_who_never_logged_in_is_safe():
    """Nothing to take out of the queue: she has no name to be in it under."""
    hub = make_lobby()
    client = FakeClient()

    hub.disconnect(hub.connect(client.send))  # connected, never said who she was

    assert client.received == []


def test_disconnecting_an_unknown_client_is_ignored():
    """Two closes for one socket, or a stale one — neither may take the server down."""
    make_lobby().disconnect(999)


def test_disconnecting_a_waiting_seeker_removes_them_from_the_queue():
    hub = make_lobby()
    lone, other = FakeClient(), FakeClient()
    lid = hub.connect(lone.send)
    login(hub, lid, "Efrat")
    hub.receive(lid, encode(Play()))  # lone is now waiting
    hub.disconnect(lid)

    oid = hub.connect(other.send)
    login(hub, oid, "Dan")
    hub.receive(oid, encode(Play()))
    assert of_type(other, Seated) == []  # the disconnected seeker was not matched


# --- disconnect -> auto-resign ------------------------------------------------

def test_a_disconnect_mid_game_tells_the_opponent_the_resign_deadline():
    """Once, with the deadline — not a countdown re-sent twenty times a second."""
    from kfchess.config import RESIGN_COUNTDOWN_MS

    hub, white, _, _, bid = seat_two()
    hub.disconnect(bid)   # black drops

    assert of_type(white, Disconnected) == [
        Disconnected(Color.BLACK, RESIGN_COUNTDOWN_MS)
    ]


def test_a_player_who_never_returns_auto_resigns_and_the_opponent_wins():
    from kfchess.config import RESIGN_COUNTDOWN_MS

    hub, white, _, _, bid = seat_two()
    hub.disconnect(bid)
    hub.tick(RESIGN_COUNTDOWN_MS)  # the countdown runs out

    snapshot = of_type(white, State)[-1].snapshot
    assert snapshot.winner is Color.WHITE
    assert snapshot.phase == "over"
    assert hub._users.get_rating("Efrat") == 1216  # winner up, via the usual ELO path
    assert hub._users.get_rating("Dan") == 1184     # loser down


# --- game over and ELO --------------------------------------------------------

def test_capturing_the_king_broadcasts_capture_then_game_over():
    hub, white, _, wid, _ = seat_two(_king_board)
    hub.receive(wid, encode(Move("WRa1a3")))  # rook -> black king
    hub.tick(100000)                          # rook arrives and captures

    events = of_type(white, Event)
    assert events[-2:] == [Event(SOUND_CAPTURE), Event(SOUND_GAME_OVER)]


def test_a_finished_game_updates_both_ratings_once_and_shows_them():
    hub, white, _, wid, _ = seat_two(_king_board)

    hub.receive(wid, encode(Move("WRa1a3")))  # rook -> black king
    hub.tick(100000)                          # capture -> game over -> ELO update

    assert hub._users.get_rating("Efrat") == 1216  # winner up
    assert hub._users.get_rating("Dan") == 1184     # loser down
    # The player does not wait on the database to see her new number: the same pair
    # rides the game-over delta, computed by the session as the king fell.
    assert of_type(white, GameOver)[-1].ratings == {
        Color.WHITE: 1216,
        Color.BLACK: 1184,
    }

    hub.tick(100000)  # a further tick must not apply the update a second time
    assert hub._users.get_rating("Efrat") == 1216


# --- resync -------------------------------------------------------------------

def test_a_full_snapshot_is_resent_on_the_resync_interval():
    """The floor under the deltas: whatever a client believes, it is corrected."""
    from kfchess.config import SNAPSHOT_RESYNC_MS

    hub, white, _, _, _ = seat_two()
    before = len(of_type(white, State))

    hub.tick(SNAPSHOT_RESYNC_MS - 1)
    assert len(of_type(white, State)) == before  # not due yet

    hub.tick(1)
    assert len(of_type(white, State)) == before + 1


# --- rooms and spectators (M6) ------------------------------------------------

def open_room(hub, creator_name="Efrat"):
    """Log in a creator and open a room; returns the creator, its id, and the room id."""
    creator, cid = login_ready(hub, creator_name)
    hub.receive(cid, encode(CreateRoom()))
    room_id = of_type(creator, Seated)[-1].room_id
    return creator, cid, room_id


def test_creating_a_room_seats_the_creator_as_white_with_a_shareable_id():
    hub = make_lobby()
    creator, _, room_id = open_room(hub)
    assert (seat(creator).color, seat(creator).room_id) == (Color.WHITE, room_id)
    assert room_id is not None
    assert of_type(creator, State)[-1].snapshot.room_id == room_id  # shown in the window


def test_joining_a_room_seats_the_second_player_as_black():
    hub = make_lobby()
    _, _, room_id = open_room(hub)
    joiner, jid = login_ready(hub, "Dan")
    hub.receive(jid, encode(JoinRoom(room_id)))
    assert (seat(joiner).color, seat(joiner).room_id) == (Color.BLACK, room_id)


def test_a_third_joiner_watches_as_a_spectator_with_no_colour():
    hub = make_lobby()
    _, _, room_id = open_room(hub)
    _, bid = login_ready(hub, "Dan")
    hub.receive(bid, encode(JoinRoom(room_id)))
    watcher, wid = login_ready(hub, "Sam")
    hub.receive(wid, encode(JoinRoom(room_id)))
    assert (seat(watcher).color, seat(watcher).room_id) == (None, room_id)


def test_a_spectator_cannot_move():
    hub = make_lobby()
    creator, cid, room_id = open_room(hub)
    _, bid = login_ready(hub, "Dan")
    hub.receive(bid, encode(JoinRoom(room_id)))
    watcher, wid = login_ready(hub, "Sam")
    hub.receive(wid, encode(JoinRoom(room_id)))

    hub.receive(wid, encode(Move("WRa1a3")))
    assert watcher.received[-1] == Rejected(RejectReason.NOT_A_PLAYER)


def test_a_spectator_still_sees_the_game_state():
    hub = make_lobby()
    creator, cid, room_id = open_room(hub)
    _, bid = login_ready(hub, "Dan")
    hub.receive(bid, encode(JoinRoom(room_id)))
    watcher, wid = login_ready(hub, "Sam")
    hub.receive(wid, encode(JoinRoom(room_id)))
    before = len(watcher.received)

    hub.receive(cid, encode(Move("WRa1a3")))  # white plays
    assert isinstance(watcher.received[-1], MoveStarted)  # the watcher was broadcast to
    assert len(watcher.received) > before


def test_joining_an_unknown_room_is_refused():
    hub = make_lobby()
    client, cid = login_ready(hub, "Efrat")
    hub.receive(cid, encode(JoinRoom("ZZZZ")))
    assert client.received[-1] == Notice(NoticeReason.NO_SUCH_ROOM)


def test_creating_or_joining_a_room_before_logging_in_is_ignored():
    hub = make_lobby()
    a, b = FakeClient(), FakeClient()
    aid, bid = hub.connect(a.send), hub.connect(b.send)
    hub.receive(aid, encode(CreateRoom()))
    hub.receive(bid, encode(JoinRoom("ZZZZ")))
    assert of_type(a, Seated) == [] and a.received == []
    assert of_type(b, Seated) == []


def test_creating_a_room_while_already_in_a_game_is_ignored():
    hub, white, _, wid, _ = seat_two()
    before = len(white.received)
    hub.receive(wid, encode(CreateRoom()))
    assert len(white.received) == before


def test_a_solo_room_game_that_ends_is_left_unrated():
    hub = make_lobby(_king_board)
    creator, cid, _ = open_room(hub)  # only the creator; nobody is black
    hub.receive(cid, encode(Move("WRa1a3")))
    hub.tick(100000)  # white captures the unowned black king -> game over
    assert of_type(creator, State)[-1].snapshot.winner is Color.WHITE
    assert hub._users.get_rating("Efrat") == START_RATING  # unrated: no opponent


# --- reconnect within the countdown -------------------------------------------

def test_reconnecting_within_the_countdown_reseats_the_player():
    hub, white, black, wid, bid = seat_two()
    hub.disconnect(bid)  # "Dan" (black) drops -> countdown starts
    returner = FakeClient()
    rid = hub.connect(returner.send)
    login(hub, rid, "Dan")  # same username, still within the window

    welcome = of_type(returner, Welcome)[-1]
    assert (welcome.color, welcome.rating) == (Color.BLACK, START_RATING)
    assert welcome.seat_token == seat(black).seat_token  # the same seat, provably
    assert of_type(returner, State)  # got the board back, straight into the game


def test_reconnecting_clears_the_opponents_countdown():
    hub, white, black, wid, bid = seat_two()
    hub.disconnect(bid)
    hub.tick(5000)  # the opponent has been watching the countdown
    assert of_type(white, Reconnected) == []

    login(hub, hub.connect(FakeClient().send), "Dan")
    assert of_type(white, Reconnected) == [Reconnected()]  # countdown cancelled


def test_a_reconnected_player_can_move_again():
    hub, white, black, wid, bid = seat_two()
    hub.disconnect(wid)  # "Efrat" (white) drops
    returner = FakeClient()
    rid = hub.connect(returner.send)
    login(hub, rid, "Efrat")

    hub.receive(rid, encode(Move("WRa1a3")))  # the white rook, now that we are back
    assert of_type(returner, Rejected) == []                 # accepted
    assert of_type(returner, MoveStarted) == [MoveStarted(0, "wR", "a1", "a3", 0, 2000)]


def test_a_brand_new_user_logs_into_the_lobby_not_a_game():
    hub, white, black, wid, bid = seat_two()  # a live game, nobody has dropped
    newbie = FakeClient()
    login(hub, hub.connect(newbie.send), "Sam")
    assert of_type(newbie, Welcome)[-1] == Welcome(None, START_RATING)  # -> the lobby
    assert of_type(newbie, State) == []                                 # not in a game


def test_a_different_user_cannot_take_a_missing_seat():
    hub, white, black, wid, bid = seat_two()
    hub.disconnect(bid)  # "Dan"'s seat is now the one mid-countdown
    eve = FakeClient()
    login(hub, hub.connect(eve.send), "Eve")  # a different person
    assert of_type(eve, Welcome)[-1] == Welcome(None, START_RATING)  # no reconnect


def test_no_reconnect_once_the_countdown_has_expired():
    from kfchess.config import RESIGN_COUNTDOWN_MS

    hub, white, black, wid, bid = seat_two()
    hub.disconnect(bid)
    hub.tick(RESIGN_COUNTDOWN_MS)  # black auto-resigns; the game is over
    returner = FakeClient()
    login(hub, hub.connect(returner.send), "Dan")
    assert of_type(returner, Welcome)[-1].color is None  # -> the lobby, not the old game
    assert of_type(returner, State) == []                # not reseated


# --- cleanup: games are discarded once empty ----------------------------------

def test_a_game_is_discarded_once_every_member_has_left():
    hub, white, black, wid, bid = seat_two()
    hub.disconnect(wid)
    assert len(hub._games) == 1  # black is still there, so the game stays
    hub.disconnect(bid)
    assert hub._games == {}      # now empty -> cleaned up


def test_a_spectator_leaving_does_not_discard_a_live_game():
    hub = make_lobby()
    _, _, room_id = open_room(hub)
    _, bid = login_ready(hub, "Dan")
    hub.receive(bid, encode(JoinRoom(room_id)))
    watcher, wid = login_ready(hub, "Sam")
    hub.receive(wid, encode(JoinRoom(room_id)))

    hub.disconnect(wid)          # the spectator leaves
    assert len(hub._games) == 1  # the two players keep the game alive


def test_discarding_a_room_game_also_forgets_its_room():
    hub = make_lobby()
    _, cid, room_id = open_room(hub)  # a lone creator opens a room, then leaves
    hub.disconnect(cid)
    assert hub._games == {}
    assert hub._rooms.game_for(room_id) is None  # the room id is freed too


# --- the async entry point is importable --------------------------------------



# --- scheduling: when does the lobby next need a tick? -------------------------

def test_a_lobby_with_no_games_has_nothing_scheduled():
    assert make_lobby().next_event_delay_ms() is None


def test_the_lobby_reports_the_soonest_event_across_its_games():
    hub, _, _, wid, _ = seat_two()
    assert hub.next_event_delay_ms() is None  # a fresh game with nobody moving

    hub.receive(wid, encode(Move("WRa1a3")))  # arrives in two seconds
    assert hub.next_event_delay_ms() == 2 * MS_PER_CELL

    hub.tick(1_500)
    assert hub.next_event_delay_ms() == 500


def test_a_second_busier_game_pulls_the_wake_up_earlier():
    hub, _, _, wid, _ = seat_two()
    hub.receive(wid, encode(Move("WRa1a3")))  # game 0: 2,000 ms out
    hub.tick(1_800)                           # ...now 200 ms out
    other_w, other_b = FakeClient(), FakeClient()
    ow, ob = hub.connect(other_w.send), hub.connect(other_b.send)
    login(hub, ow, "Sam")
    login(hub, ob, "Noa")
    hub.receive(ow, encode(Play()))
    hub.receive(ob, encode(Play()))
    hub.receive(ow, encode(Move("WRa1a3")))   # game 1: 2,000 ms out

    assert hub.next_event_delay_ms() == 200   # the one that is closest wins


# --- rooms: the id space running out ------------------------------------------

def test_a_room_that_cannot_get_an_id_is_refused_instead_of_hanging():
    hub = Lobby(_rook_board, UserStore(":memory:"), SharedState.on(generate_id=lambda: "AAAAAA"))
    first, first_id = login_ready(hub, "Efrat")
    hub.receive(first_id, encode(CreateRoom()))  # takes the only id there is
    assert of_type(first, Seated)[-1].room_id == "AAAAAA"

    second, second_id = login_ready(hub, "Dan")
    hub.receive(second_id, encode(CreateRoom()))

    assert second.received[-1] == Notice(NoticeReason.ROOM_UNAVAILABLE)
    assert of_type(second, Seated) == []  # and it was not seated in a half-made game


def test_a_refused_room_leaves_the_player_free_to_do_something_else():
    """The half-made game is dropped, so the player is still in the lobby, not stuck."""
    hub = Lobby(_rook_board, UserStore(":memory:"), SharedState.on(generate_id=lambda: "AAAAAA"))
    _, first_id = login_ready(hub, "Efrat")
    hub.receive(first_id, encode(CreateRoom()))  # takes the only id there is
    refused, refused_id = login_ready(hub, "Dan")
    hub.receive(refused_id, encode(CreateRoom()))  # refused

    other, other_id = login_ready(hub, "Sam")
    hub.receive(refused_id, encode(Play()))
    hub.receive(other_id, encode(Play()))

    assert seat(refused).color is Color.WHITE  # matched normally
    assert seat(other).color is Color.BLACK


# --- addressing a room instead of each of its members --------------------------

def test_a_rooms_traffic_is_published_once_however_many_are_watching():
    """Running as a shard: two players and two spectators cost one message, not four."""
    published = []
    hub = Lobby(_rook_board, UserStore(":memory:"), SharedState.on(generate_id=lambda: "AAAAAA"),
                to_room=lambda subject, text: published.append((subject, text)))
    creator, cid = login_ready(hub, "Efrat")
    hub.receive(cid, encode(CreateRoom()))
    for name in ("Dan", "Sam", "Noa"):     # black, then two watchers
        _, joiner_id = login_ready(hub, name)
        hub.receive(joiner_id, encode(JoinRoom("AAAAAA")))
    published.clear()

    hub.receive(cid, encode(Move("WRa1a3")))

    # One delta, published once -- the fan-out to the four of them is the gateways' job.
    assert [subject for subject, _ in published] == [
        f"room.{hub.room_key(0)}.delta",
        f"room.{hub.room_key(0)}.delta",
    ]
    assert isinstance(decode(published[-1][1]), MoveStarted)


def test_a_seat_is_still_answered_to_the_one_client_who_asked():
    """Per-client replies do not go to the room: only that player is told her colour."""
    published = []
    hub = Lobby(_rook_board, UserStore(":memory:"),
                to_room=lambda subject, text: published.append((subject, text)))
    creator, cid = login_ready(hub, "Efrat")
    hub.receive(cid, encode(CreateRoom()))

    assert of_type(creator, Seated) != []                      # she was told
    assert all("seated" not in text for _, text in published)  # the room was not


def test_logging_in_again_reclaims_a_seat_whose_gateway_died():
    """A killed gateway cannot report its sockets closed, so nobody is mid-countdown.

    The seat is still there with the player's name on it, and logging in again -- which
    means passing the password check again -- is what takes it back.
    """
    hub, white, black, wid, bid = seat_two()
    hub.receive(wid, encode(Move("WRa1a3")))  # a game genuinely in progress

    returner = FakeClient()
    hub.receive(hub.connect(returner.send), encode(Login("Efrat", "pw")))

    assert of_type(returner, Welcome)[-1].color is Color.WHITE  # back in her seat
    assert of_type(returner, State) != []                       # and shown the board


def test_the_displaced_connection_no_longer_holds_the_seat():
    """One seat, one owner: the socket that was superseded is detached from the game."""
    hub, white, black, wid, bid = seat_two()
    returner = FakeClient()
    hub.receive(hub.connect(returner.send), encode(Login("Efrat", "pw")))
    before = len(white.received)

    hub.receive(wid, encode(Move("WRa1a3")))  # the old connection tries to play on

    assert white.received[-1] == Rejected(RejectReason.NOT_A_PLAYER)
    assert len(white.received) == before + 1  # and it hears nothing of the game


# --- resuming a seat: the cheap way back ---------------------------------------

def test_resuming_with_the_right_token_puts_her_back_without_a_password():
    """The point of the token: no hundred thousand hash rounds on a flaky network."""
    hub, white, black, wid, bid = seat_two()
    token = seat(black).seat_token
    hub.disconnect(bid)

    returner = FakeClient()
    hub.receive(hub.connect(returner.send), encode(Resume("Dan", token)))

    assert of_type(returner, Welcome)[-1].color is Color.BLACK
    assert of_type(returner, State) != []                # and shown the board
    assert of_type(white, Reconnected) != []             # her opponent's countdown ends


def test_a_wrong_token_is_refused_by_the_shard_that_issued_the_right_one():
    """Knowing the username is not enough, which is the whole reason a token exists."""
    hub, white, black, wid, bid = seat_two()
    hub.disconnect(bid)

    impostor = FakeClient()
    hub.receive(hub.connect(impostor.send), encode(Resume("Dan", "not-the-token")))

    assert impostor.received[-1] == Rejected(RejectReason.BAD_SEAT)
    assert of_type(impostor, Welcome) == []
    assert of_type(white, Reconnected) == []  # and Dan's countdown is still running


def test_resuming_a_seat_nobody_holds_is_refused_the_same_way():
    """One answer for every failure, so a caller cannot map the seats it does not hold."""
    hub = make_lobby()
    stranger = FakeClient()

    hub.receive(hub.connect(stranger.send), encode(Resume("Nobody", "made-up")))

    assert stranger.received[-1] == Rejected(RejectReason.BAD_SEAT)


def test_a_seat_on_another_shard_is_not_resumable_here():
    """The directory is shared; the games are not. This shard can only seat its own."""
    store = InMemoryKeyValueStore()
    here = Lobby(_rook_board, UserStore(":memory:"), SharedState.on(store, "sh1"))
    elsewhere = PlayerDirectory(store)
    away = elsewhere.take_seat("Dan", "0", "sh2", Color.BLACK)

    client = FakeClient()
    here.receive(here.connect(client.send), encode(Resume("Dan", away.seat_token)))

    assert client.received[-1] == Rejected(RejectReason.BAD_SEAT)


def test_a_finished_game_is_forgotten_so_the_next_login_starts_fresh():
    """Her seat outlived the game only long enough for the last person to leave it."""
    store = InMemoryKeyValueStore()
    hub = Lobby(_rook_board, UserStore(":memory:"), SharedState.on(store))
    white, wid = login_ready(hub, "Efrat")
    black, bid = login_ready(hub, "Dan")
    hub.receive(wid, encode(Play()))
    hub.receive(bid, encode(Play()))

    hub.disconnect(wid)
    hub.disconnect(bid)  # the last one out; the game is discarded

    assert PlayerDirectory(store).seat_of("Efrat") is None
    assert PlayerDirectory(store).seat_of("Dan") is None


def test_a_spectator_gets_no_seat_and_no_token():
    """There is nothing to come back to, so nothing is written down."""
    store = InMemoryKeyValueStore()
    hub = Lobby(
        _rook_board, UserStore(":memory:"),
        SharedState.on(store, generate_id=lambda: "AAAAAA"),
    )
    _, creator_id = login_ready(hub, "Efrat")
    hub.receive(creator_id, encode(CreateRoom()))
    for name in ("Dan", "Sam"):
        watcher, joiner_id = login_ready(hub, name)
        hub.receive(joiner_id, encode(JoinRoom("AAAAAA")))

    assert seat(watcher).color is None
    assert seat(watcher).seat_token == ""
    assert PlayerDirectory(store).seat_of("Sam") is None


def test_a_partner_waiting_on_another_shard_is_left_in_the_queue():
    """Until S4.3 can hand the match to a shard that holds both, neither is stranded.

    The pairing is real — the queue is shared — but this lobby cannot seat somebody whose
    connection it does not hold. Dropping her would be the easy wrong answer: she pressed
    Play and is owed a game. So she goes back in, and the next seeker who can seat her will.
    """
    store = InMemoryKeyValueStore()
    users = UserStore(":memory:")
    here = Lobby(_rook_board, users, SharedState.on(store, "sh1"))
    there = Lobby(_rook_board, users, SharedState.on(store, "sh2"))

    away, away_id = login_ready(there, "Efrat")
    there.receive(away_id, encode(Play()))  # she waits, on the other shard
    mine, my_id = login_ready(here, "Dan")
    here.receive(my_id, encode(Play()))  # matched with her -- and unseatable from here

    assert of_type(mine, Seated) == []
    assert of_type(away, Seated) == []
    assert SharedState.on(store).matchmaker.is_waiting("Efrat")  # still there for the next one


def test_a_joiner_sent_here_for_a_room_that_has_since_ended_is_told_so():
    """The race: the last person left the room between her being redirected and arriving."""
    hub = make_lobby()
    joiner, joiner_id = login_ready(hub, "Dan")

    hub.join_game(joiner_id, "Dan", START_RATING, "AAAAAA")

    assert joiner.received[-1] == Notice(NoticeReason.NO_SUCH_ROOM)
    assert of_type(joiner, Seated) == []


def test_an_answer_for_a_client_who_left_during_the_check_is_dropped():
    """A password check is 36 ms away now, which is ample time for a socket to close.

    Nothing could happen in the middle of a login when the hashing was inline. It can
    now, and the answer arriving for somebody who has gone must not resurrect her.
    """
    hub = make_lobby()
    client = FakeClient()
    client_id = hub.connect(client.send)
    hub.disconnect(client_id)

    hub.authenticated(client_id, "Efrat", START_RATING)

    assert client.received == []


def test_a_player_already_in_a_game_is_not_seated_into_a_second_one():
    """The floor under a race, not a fix for one.

    A departure removes her only from the game her seat records, so a player in two games
    leaves one of them for ever — and a game with a member who never leaves is a game
    nothing ever discards. A matchmaking race did exactly this in a two-shard deployment.
    """
    hub, white, black, wid, bid = seat_two()
    first_game = of_type(white, State)[-1].snapshot

    hub.start_game((wid, "Efrat", START_RATING), (bid, "Dan", START_RATING))

    # No second seat, and the game she is in is the one she was already in.
    assert len(of_type(white, Seated)) == 1
    assert of_type(white, State)[-1].snapshot.room_id == first_game.room_id
