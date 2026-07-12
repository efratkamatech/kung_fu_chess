from kfchess.engine.arbiter import Motion, RealTimeArbiter
from kfchess.model.board import Board
from kfchess.model.color import Color
from kfchess.model.piece import Piece, PieceState
from kfchess.model.piece_type import PieceType
from kfchess.model.position import Position

MS_PER_CELL = 1000


def rook(color=Color.WHITE):
    return Piece(PieceType("R", "x"), color)


def board_with_rook():
    board = Board(1, 3)
    board.place(Position(0, 0), rook())
    return board


def test_motion_records_its_fields():
    motion = Motion(rook(), Position(0, 0), Position(0, 2), 2000)
    assert motion.source == Position(0, 0)
    assert motion.target == Position(0, 2)
    assert motion.arrival_ms == 2000


def test_start_motion_keeps_piece_at_origin_and_marks_it_moving():
    board = board_with_rook()
    piece = board.piece_at(Position(0, 0))
    RealTimeArbiter(board, MS_PER_CELL).start_motion(
        piece, Position(0, 0), Position(0, 2), now_ms=0
    )
    assert board.piece_at(Position(0, 0)) is piece  # still at origin
    assert piece.state is PieceState.MOVING


def test_resolve_before_arrival_does_nothing():
    board = board_with_rook()
    piece = board.piece_at(Position(0, 0))
    arbiter = RealTimeArbiter(board, MS_PER_CELL)
    arbiter.start_motion(piece, Position(0, 0), Position(0, 2), now_ms=0)  # arrives 2000
    arbiter.resolve(1000)  # too early
    assert board.piece_at(Position(0, 0)) is piece
    assert board.is_empty(Position(0, 2))
    assert piece.state is PieceState.MOVING


def test_resolve_at_arrival_relocates_and_returns_to_idle():
    board = board_with_rook()
    piece = board.piece_at(Position(0, 0))
    arbiter = RealTimeArbiter(board, MS_PER_CELL)
    arbiter.start_motion(piece, Position(0, 0), Position(0, 2), now_ms=0)
    arbiter.resolve(2000)
    assert board.is_empty(Position(0, 0))
    assert board.piece_at(Position(0, 2)) is piece
    assert piece.state is PieceState.IDLE


def test_arriving_piece_captures_a_settled_piece_at_the_destination():
    board = Board(1, 3)
    mover = rook(Color.WHITE)
    board.place(Position(0, 0), mover)
    board.place(Position(0, 2), rook(Color.BLACK))  # enemy settled on the destination
    arbiter = RealTimeArbiter(board, MS_PER_CELL)
    arbiter.start_motion(mover, Position(0, 0), Position(0, 2), now_ms=0)
    arbiter.resolve(2000)
    assert board.piece_at(Position(0, 2)) is mover  # captured
