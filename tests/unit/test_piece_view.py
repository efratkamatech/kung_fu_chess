from kfchess.config import STATE_IDLE, STATE_LONG_REST, STATE_MOVE
from kfchess.graphics.piece_view import PieceView
from kfchess.model.color import Color
from kfchess.model.piece import Piece, PieceState
from kfchess.model.piece_type import PieceType


def a_piece():
    return Piece(PieceType("P", "pawn"), Color.WHITE)


def test_maps_core_state_to_animation_folder():
    view = PieceView()
    piece = a_piece()
    assert view.state_and_elapsed(piece, 0)[0] == STATE_IDLE
    piece.state = PieceState.MOVING
    assert view.state_and_elapsed(piece, 0)[0] == STATE_MOVE
    piece.state = PieceState.COOLDOWN
    assert view.state_and_elapsed(piece, 0)[0] == STATE_LONG_REST


def test_elapsed_grows_while_state_is_unchanged():
    view = PieceView()
    piece = a_piece()
    view.state_and_elapsed(piece, 1000)          # enters idle at t=1000
    assert view.state_and_elapsed(piece, 1300)[1] == 300


def test_elapsed_resets_on_state_change():
    view = PieceView()
    piece = a_piece()
    view.state_and_elapsed(piece, 1000)          # idle since 1000
    piece.state = PieceState.MOVING
    state, elapsed = view.state_and_elapsed(piece, 1200)  # transition at 1200
    assert (state, elapsed) == (STATE_MOVE, 0)
