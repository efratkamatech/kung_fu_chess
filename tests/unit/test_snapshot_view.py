"""Tests for rebuilding renderer inputs from a GameSnapshot."""

from kfchess.client.snapshot_view import SnapshotHudSource, to_render_inputs
from kfchess.model.color import Color
from kfchess.model.piece import PieceState
from kfchess.model.position import Position
from kfchess.snapshot import CellView, GameSnapshot, MovingView


def a_snapshot():
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
        names={},
        ratings={},
        phase="playing",
        winner=None,
        now_ms=5,
    )


def test_cells_rebuild_pieces_with_their_state():
    board, _, _ = to_render_inputs(a_snapshot())
    king = board.piece_at(Position(0, 0))
    rook = board.piece_at(Position(1, 1))
    assert king.piece_type.letter == "K" and king.color is Color.WHITE
    assert king.state is PieceState.IDLE
    assert rook.state is PieceState.COOLDOWN
    assert board.piece_at(Position(0, 1)) is None  # empty cells stay empty


def test_cooldown_fraction_is_carried_for_cooling_pieces():
    board, _, cooldowns = to_render_inputs(a_snapshot())
    rook = board.piece_at(Position(1, 1))
    assert cooldowns == {rook: 0.5}  # only the cooling rook, at its fraction


def test_moving_pieces_become_the_overlay():
    _, moving, _ = to_render_inputs(a_snapshot())
    assert len(moving) == 1
    assert moving[0].piece.state is PieceState.MOVING
    assert moving[0].position == (1.5, 0.0)


def test_hud_source_reads_scores_and_logs_from_the_snapshot():
    source = SnapshotHudSource()
    assert source.score(Color.WHITE) == 0     # nothing before the first snapshot
    assert source.recent(Color.WHITE, 5) == []

    source.update(a_snapshot())
    assert source.score(Color.WHITE) == 9
    assert source.recent(Color.WHITE, 1) == ["x bN"]  # most recent line only


def test_hud_source_reads_names_or_none_when_not_logged_in():
    from dataclasses import replace

    source = SnapshotHudSource()
    assert source.name(Color.WHITE) is None            # nothing before the first snapshot

    source.update(a_snapshot())                        # names is empty here
    assert source.name(Color.WHITE) is None            # nobody has logged in yet

    source.update(replace(a_snapshot(), names={Color.WHITE: "Efrat"}))
    assert source.name(Color.WHITE) == "Efrat"
    assert source.name(Color.BLACK) is None            # black still hasn't
