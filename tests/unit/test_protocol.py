"""Tests for the wire protocol: every message survives encode -> decode unchanged."""

import pytest

from kfchess.model.color import Color
from kfchess.protocol import (
    Assigned,
    Event,
    Login,
    Move,
    Notice,
    Play,
    ProtocolError,
    Rejected,
    Seated,
    State,
    Welcome,
    decode,
    encode,
)
from kfchess.snapshot import CellView, GameSnapshot


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
        phase="playing",
        winner=None,
        now_ms=0,
    )


@pytest.mark.parametrize(
    "message",
    [
        Move("WQe2e5"),
        Login("Efrat", "secret"),
        Assigned(Color.BLACK),
        Welcome(Color.WHITE, 1200),
        Welcome(None, 1350),  # a spectator: no colour
        Rejected("bad_password"),
        State(a_snapshot()),
        Event("capture"),
        Play(),
        Seated(Color.WHITE),
        Seated(None),  # a spectator: no colour
        Notice("no_opponent"),
    ],
)
def test_encode_then_decode_round_trips(message):
    assert decode(encode(message)) == message


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
