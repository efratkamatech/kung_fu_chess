from kfchess.engine.arbiter import RealTimeArbiter
from kfchess.engine.clock import Clock
from kfchess.engine.game_engine import GameEngine
from kfchess.model.board import Board
from kfchess.model.color import Color
from kfchess.model.piece import Piece, PieceState
from kfchess.model.piece_type import PieceType
from kfchess.model.position import Position
from kfchess.movement.rules import standard_movement_rules
from kfchess.rules.rule_engine import RuleEngine

MS_PER_CELL = 1000


def make_engine(board, clock=None):
    clock = clock or Clock()
    return GameEngine(
        board,
        clock,
        RuleEngine(standard_movement_rules()),
        RealTimeArbiter(board, MS_PER_CELL),
    )


def rook_board():
    board = Board(3, 3)
    board.place(Position(0, 0), Piece(PieceType("R", "rook"), Color.WHITE))
    return board


def test_board_property_exposes_the_board():
    board = Board(2, 2)
    assert make_engine(board).board is board


def test_legal_move_is_still_in_flight_before_arrival():
    board = rook_board()
    engine = make_engine(board)
    engine.request_move(Position(0, 0), Position(0, 2))  # 2 cells -> arrives at 2000
    engine.wait(1000)  # not enough time
    assert board.piece_at(Position(0, 0)).piece_type.letter == "R"  # still at origin
    assert board.is_empty(Position(0, 2))


def test_legal_move_completes_after_enough_time():
    board = rook_board()
    engine = make_engine(board)
    engine.request_move(Position(0, 0), Position(0, 2))
    engine.wait(2000)
    assert board.is_empty(Position(0, 0))
    assert board.piece_at(Position(0, 2)).piece_type.letter == "R"


def test_moving_piece_is_marked_moving_then_idle():
    board = rook_board()
    engine = make_engine(board)
    piece = board.piece_at(Position(0, 0))
    engine.request_move(Position(0, 0), Position(0, 2))
    assert piece.state is PieceState.MOVING
    engine.wait(2000)
    assert piece.state is PieceState.IDLE


def test_illegal_move_starts_no_motion():
    board = rook_board()
    engine = make_engine(board)
    engine.request_move(Position(0, 0), Position(1, 1))  # rook diagonal: illegal
    engine.wait(5000)
    assert board.piece_at(Position(0, 0)).piece_type.letter == "R"  # never left
    assert board.is_empty(Position(1, 1))


def test_wait_advances_the_clock():
    clock = Clock()
    make_engine(Board(2, 2), clock).wait(750)
    assert clock.now_ms == 750


def test_moving_piece_cannot_be_redirected():
    board = rook_board()
    engine = make_engine(board)
    engine.request_move(Position(0, 0), Position(0, 2))  # 2-cell move, arrives 2000
    engine.wait(500)                                     # in flight
    engine.request_move(Position(0, 0), Position(0, 1))  # redirect attempt -> ignored
    engine.wait(2000)                                    # original completes
    assert board.piece_at(Position(0, 2)).piece_type.letter == "R"  # original target
    assert board.is_empty(Position(0, 1))


def test_no_cooldown_move_again_immediately_after_arrival():
    board = rook_board()
    engine = make_engine(board)
    engine.request_move(Position(0, 0), Position(0, 1))  # arrives 1000
    engine.wait(1000)
    engine.request_move(Position(0, 1), Position(0, 2))  # move again right away
    engine.wait(1000)
    assert board.piece_at(Position(0, 2)).piece_type.letter == "R"
    assert board.is_empty(Position(0, 0))
    assert board.is_empty(Position(0, 1))
