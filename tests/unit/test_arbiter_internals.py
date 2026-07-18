"""White-box tests for a few arbiter internals: the Motion value object's degenerate
(zero-distance) cases and the cooldown-progress guard for zero-length cooldowns."""

from kfchess.app.bootstrap import build_game
from kfchess.engine.arbiter import Cooldown, Motion, RealTimeArbiter
from kfchess.model.board import Board
from kfchess.model.color import Color
from kfchess.model.piece import Piece
from kfchess.model.piece_type import PieceType, standard_piece_types
from kfchess.model.position import Position
from kfchess.movement.rules import PAWN_FORWARD
from kfchess.rules.promotion import Promotion


def a_piece():
    return Piece(PieceType("R", "rook"), Color.WHITE)


def test_motion_position_at_instant_move_clamps_to_the_target():
    motion = Motion(a_piece(), Position(2, 2), Position(2, 2), 0, 0, sequence=0)  # span 0
    assert motion.position_at(9) == (2.0, 2.0)


def test_motion_cell_timeline_zero_distance_is_just_its_cell():
    motion = Motion(a_piece(), Position(1, 1), Position(1, 1), 0, 0, sequence=0)
    assert motion.cell_timeline() == [(Position(1, 1), 0, 0)]


def an_arbiter():
    promotion = Promotion(PAWN_FORWARD, PieceType("Q", "queen"))
    return RealTimeArbiter(Board(3, 3), 1000, promotion, 1000, 1000)


def test_cooldown_progress_omits_zero_length_cooldowns():
    arbiter = an_arbiter()
    arbiter._cooldowns.append(Cooldown(a_piece(), ready_ms=100, started_ms=100, duration_ms=0))
    assert arbiter.cooldown_progress(50) == {}


def test_a_piece_captured_on_arrival_cancels_its_own_motion():
    # White and black rooks both arrive at t=1000. White (started first) lands on the
    # black rook's cell and captures it, so the black rook's own arriving motion is
    # cancelled rather than resolved.
    reg = standard_piece_types()
    grid = [[Piece(reg.get("R"), Color.WHITE), Piece(reg.get("R"), Color.BLACK), None]]
    engine, _ = build_game(Board.from_grid(grid))

    engine.request_move(Position(0, 0), Position(0, 1))  # white captures black's cell
    engine.request_move(Position(0, 1), Position(0, 2))  # black flees (started second)
    engine.wait(1000)                                    # both arrive together

    assert engine.board.piece_at(Position(0, 1)).color is Color.WHITE  # white landed
    assert engine.board.is_empty(Position(0, 2))  # black was captured, never arrived
