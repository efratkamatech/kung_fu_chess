"""Tests for the wire protocol: every message survives encode -> decode unchanged."""

import pytest

from kfchess.model.color import Color
from kfchess.shared.protocol import (
    Captured,
    CooldownDone,
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
    ProtocolError,
    Reconnected,
    Rejected,
    Seated,
    Settled,
    State,
    Welcome,
    decode,
    encode,
)
from kfchess.shared.snapshot import CellView, GameSnapshot
from kfchess.shared.codes import NoticeReason, Phase, RejectReason


def a_snapshot():
    return GameSnapshot(
        rows=1,
        cols=1,
        cells=[[CellView("wK", "IDLE")]],
        moving=[],
        scores={Color.WHITE: 0, Color.BLACK: 0},
        logs={Color.WHITE: [], Color.BLACK: []},
        names={},
        ratings={},
        phase=Phase.PLAYING,
        winner=None,
        now_ms=0,
    )


@pytest.mark.parametrize(
    "message",
    [
        Move("WQe2e5"),
        Login("Efrat", "secret"),
        Welcome(Color.WHITE, 1200),
        Welcome(None, 1350),  # a spectator: no colour
        Rejected(RejectReason.BAD_PASSWORD),
        State(a_snapshot()),
        Event("capture"),
        Play(),
        Seated(Color.WHITE),
        Seated(None),  # a spectator: no colour
        Seated(Color.BLACK, "7C2F"),  # seated via a room, with its id
        Notice(NoticeReason.NO_OPPONENT),
        CreateRoom(),
        JoinRoom("7C2F"),
        # --- the deltas ---
        MoveStarted(7, "wQ", "e2", "e5", 1000, 4000),
        Settled(7, "wQ", "e5", 4000, 1000),
        Settled(3, "wQ", "e8", 9000, 1000),  # a pawn that settled as a promoted queen
        Captured(9, "bP", 4000),
        CooldownDone(7, 5000),
        GameOver(Color.WHITE, 12345, {Color.WHITE: 1216, Color.BLACK: 1184}),
        GameOver(None, 12345),               # an unrated game: no new ratings
        Disconnected(Color.BLACK, 30000),
        Reconnected(),
    ],
)
def test_encode_then_decode_round_trips(message):
    assert decode(encode(message)) == message


def a_full_board_snapshot():
    """A snapshot of a populated 8x8 board — the size a real broadcast actually is."""
    return GameSnapshot(
        rows=8,
        cols=8,
        cells=[[CellView("wP", "IDLE") for _ in range(8)] for _ in range(8)],
        moving=[],
        scores={Color.WHITE: 0, Color.BLACK: 0},
        logs={Color.WHITE: [], Color.BLACK: []},
        names={Color.WHITE: "efrat", Color.BLACK: "noa"},
        ratings={Color.WHITE: 1200, Color.BLACK: 1213},
        phase=Phase.PLAYING,
        winner=None,
        now_ms=0,
    )


def test_a_delta_is_far_smaller_than_the_snapshot_it_replaces():
    """The whole point of S0: announce the move, don't re-send the board.

    The measured figures behind the design are ~2,148 bytes for a real opening-position
    snapshot against ~110 for a move — and that snapshot used to go out twenty times a
    second. Asserted as an order of magnitude rather than a pinned number, which would
    move with the board.
    """
    delta = encode(MoveStarted(7, "wQ", "e2", "e5", 1000, 4000))
    assert len(delta) * 10 < len(encode(State(a_full_board_snapshot())))


def test_login_password_defaults_to_empty_when_absent():
    assert decode('{"type": "login", "username": "Efrat"}') == Login("Efrat", "")


def test_encode_produces_a_json_string():
    assert encode(Move("WQe2e5")) == '{"type": "move", "cmd": "WQe2e5"}'


def test_decode_rejects_an_unknown_type():
    with pytest.raises(ProtocolError):
        decode('{"type": "spaghetti"}')


def test_decode_rejects_a_message_with_no_type():
    with pytest.raises(ProtocolError):
        decode('{"cmd": "WQe2e5"}')
