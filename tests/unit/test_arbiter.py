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
    motion = Motion(rook(), Position(0, 0), Position(0, 2), 0, 2000, 0)
    assert motion.source == Position(0, 0)
    assert motion.target == Position(0, 2)
    assert motion.start_ms == 0
    assert motion.arrival_ms == 2000
    assert motion.sequence == 0


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


def test_two_enemies_crossing_the_one_that_started_first_wins():
    board = Board(1, 4)
    white = rook(Color.WHITE)
    black = rook(Color.BLACK)
    board.place(Position(0, 0), white)
    board.place(Position(0, 3), black)
    arbiter = RealTimeArbiter(board, MS_PER_CELL)
    arbiter.start_motion(white, Position(0, 0), Position(0, 3), now_ms=0)  # started first
    arbiter.start_motion(black, Position(0, 3), Position(0, 0), now_ms=0)  # started second
    arbiter.resolve(3000)  # both arrive together; white (first) captures black
    assert board.piece_at(Position(0, 3)) is white
    assert board.is_empty(Position(0, 0))
    assert board.is_empty(Position(0, 1))
    assert board.is_empty(Position(0, 2))


def test_capturing_a_moving_piece_cancels_its_in_flight_motion():
    board = Board(1, 4)
    white = rook(Color.WHITE)
    black = rook(Color.BLACK)
    board.place(Position(0, 2), white)
    board.place(Position(0, 3), black)
    arbiter = RealTimeArbiter(board, MS_PER_CELL)
    arbiter.start_motion(black, Position(0, 3), Position(0, 0), now_ms=0)  # arrives 3000
    arbiter.start_motion(white, Position(0, 2), Position(0, 3), now_ms=0)  # arrives 1000
    arbiter.resolve(1000)  # white reaches black's cell first and captures it
    assert board.piece_at(Position(0, 3)) is white
    arbiter.resolve(3000)  # black's motion was cancelled, so nothing reappears
    assert board.piece_at(Position(0, 3)) is white
    assert board.is_empty(Position(0, 0))
