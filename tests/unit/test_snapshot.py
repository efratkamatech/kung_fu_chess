"""Tests for GameSnapshot: it survives a round-trip to JSON and back unchanged."""

import json
from dataclasses import replace

from kfchess.model.color import Color
from kfchess.snapshot import CellView, GameSnapshot, MovingView


def a_snapshot(winner=Color.WHITE):
    return GameSnapshot(
        rows=2,
        cols=2,
        cells=[
            [CellView("wK", "IDLE"), None],
            [None, CellView("bR", "COOLDOWN", cooldown=0.5)],
        ],
        moving=[MovingView("wP", row=1.5, col=0.0)],
        scores={Color.WHITE: 9, Color.BLACK: 0},
        logs={Color.WHITE: ["wP a2 -> a4", "x bN"], Color.BLACK: []},
        names={Color.WHITE: "Efrat", Color.BLACK: "Dan"},
        ratings={Color.WHITE: 1200, Color.BLACK: 1200},
        phase="playing",
        winner=winner,
        now_ms=1234,
    )


def test_round_trip_through_json_is_unchanged():
    snapshot = a_snapshot()
    restored = GameSnapshot.from_dict(json.loads(json.dumps(snapshot.to_dict())))
    assert restored == snapshot


def test_cooldown_defaults_to_zero_when_omitted():
    assert CellView("wK", "IDLE").cooldown == 0.0


def test_colours_serialise_to_their_prefix():
    data = a_snapshot().to_dict()
    assert set(data["scores"]) == {"w", "b"}  # keyed by the one-letter colour prefix
    assert data["winner"] == "w"


def test_a_drawn_game_has_no_winner():
    snapshot = a_snapshot(winner=None)
    restored = GameSnapshot.from_dict(json.loads(json.dumps(snapshot.to_dict())))
    assert restored.winner is None
    assert restored == snapshot


def test_a_sparse_names_dict_round_trips_when_only_one_side_has_logged_in():
    snapshot = replace(a_snapshot(), names={Color.WHITE: "Efrat"})
    restored = GameSnapshot.from_dict(json.loads(json.dumps(snapshot.to_dict())))
    assert restored.names == {Color.WHITE: "Efrat"}  # black has not logged in yet
