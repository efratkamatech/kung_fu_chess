"""Tests for the wire protocol: every message survives encode -> decode unchanged."""

import pytest

from kfchess.model.color import Color
from kfchess.protocol import (
    Assigned,
    Move,
    ProtocolError,
    Rejected,
    State,
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
        phase="playing",
        winner=None,
        now_ms=0,
    )


@pytest.mark.parametrize(
    "message",
    [
        Move("WQe2e5"),
        Assigned(Color.BLACK),
        Rejected("not_your_piece"),
        State(a_snapshot()),
    ],
)
def test_encode_then_decode_round_trips(message):
    assert decode(encode(message)) == message


def test_encode_produces_a_json_string():
    assert encode(Move("WQe2e5")) == '{"type": "move", "cmd": "WQe2e5"}'


def test_decode_rejects_an_unknown_type():
    with pytest.raises(ProtocolError):
        decode('{"type": "spaghetti"}')


def test_decode_rejects_a_message_with_no_type():
    with pytest.raises(ProtocolError):
        decode('{"cmd": "WQe2e5"}')
