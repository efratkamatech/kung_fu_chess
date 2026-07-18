from kfchess.engine.arbiter import RealTimeArbiter
from kfchess.engine.clock import Clock
from kfchess.engine.game_engine import GameEngine
from kfchess.model.board import Board
from kfchess.model.color import Color
from kfchess.model.piece import Piece, PieceState
from kfchess.model.piece_type import PieceType
from kfchess.model.position import Position
from kfchess.movement.rules import PAWN_FORWARD, standard_movement_rules
from kfchess.rules.promotion import Promotion
from kfchess.rules.rule_engine import RuleEngine

MS_PER_CELL = 1000
JUMP_DURATION_MS = 1000
COOLDOWN_MS = 1000
PROMOTION = Promotion(PAWN_FORWARD, PieceType("Q", "queen"))


def make_engine(board, clock=None):
    clock = clock or Clock()
    return GameEngine(
        board,
        clock,
        RuleEngine(standard_movement_rules()),
        RealTimeArbiter(board, MS_PER_CELL, PROMOTION, JUMP_DURATION_MS, COOLDOWN_MS),
    )


def rook_board():
    board = Board(3, 3)
    board.place(Position(0, 0), Piece(PieceType("R", "rook"), Color.WHITE))
    return board


def test_board_property_exposes_the_board():
    board = Board(2, 2)
    assert make_engine(board).board is board


def test_now_ms_tracks_the_clock():
    engine = make_engine(Board(2, 2))
    assert engine.now_ms == 0
    engine.wait(1234)
    assert engine.now_ms == 1234


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


def test_moving_pieces_uses_the_current_clock_time():
    board = rook_board()
    engine = make_engine(board)
    assert engine.moving_pieces() == []                  # nothing moving at rest
    engine.request_move(Position(0, 0), Position(0, 2))  # 2 cells, arrives at 2000
    engine.wait(1000)                                    # clock now at 1000 -> halfway

    snapshot = engine.moving_pieces()
    assert len(snapshot) == 1
    assert snapshot[0].position == (0.0, 1.0)            # interpolated at the clock time
    assert snapshot[0].source == Position(0, 0)
    assert snapshot[0].target == Position(0, 2)

    engine.wait(1000)                                    # clock at 2000 -> arrived, out of flight
    assert engine.moving_pieces() == []


def test_moving_piece_is_marked_moving_then_cooldown_then_idle():
    board = rook_board()
    engine = make_engine(board)
    piece = board.piece_at(Position(0, 0))
    engine.request_move(Position(0, 0), Position(0, 2))
    assert piece.state is PieceState.MOVING
    engine.wait(2000)                       # arrives -> on cooldown, not yet free
    assert piece.state is PieceState.COOLDOWN
    engine.wait(1000)                       # cooldown elapses
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


def test_cooldown_blocks_an_immediate_second_move_but_allows_a_later_one():
    board = rook_board()
    engine = make_engine(board)
    engine.request_move(Position(0, 0), Position(0, 1))  # arrives 1000
    engine.wait(1000)                                    # lands -> on cooldown until 2000
    engine.request_move(Position(0, 1), Position(0, 2))  # too soon -> rejected
    engine.wait(500)                                     # now 1500, still cooling
    assert board.piece_at(Position(0, 1)).piece_type.letter == "R"  # did not move
    assert board.is_empty(Position(0, 2))
    engine.wait(500)                                     # now 2000, cooldown elapsed
    engine.request_move(Position(0, 1), Position(0, 2))  # now allowed, arrives 3000
    engine.wait(1000)
    assert board.piece_at(Position(0, 2)).piece_type.letter == "R"
    assert board.is_empty(Position(0, 1))


def test_no_moves_after_the_king_is_captured():
    board = Board(2, 3)
    board.place(Position(0, 0), Piece(PieceType("R", "rook"), Color.WHITE))
    board.place(Position(0, 2), Piece(PieceType("K", "king", is_king=True), Color.BLACK))
    black_rook = Piece(PieceType("R", "rook"), Color.BLACK)
    board.place(Position(1, 0), black_rook)
    engine = make_engine(board)

    engine.request_move(Position(0, 0), Position(0, 2))  # white rook captures the king
    engine.wait(2000)                                    # -> game over
    engine.request_move(Position(1, 0), Position(1, 1))  # ignored
    engine.wait(1000)                                    # ignored
    assert board.piece_at(Position(1, 0)) is black_rook  # black rook never moved
    assert board.is_empty(Position(1, 1))


def test_request_jump_makes_a_piece_jump():
    board = Board(3, 3)
    piece = Piece(PieceType("K", "king"), Color.WHITE)
    board.place(Position(1, 1), piece)
    make_engine(board).request_jump(Position(1, 1))
    assert piece.state is PieceState.JUMPING


def test_request_jump_on_an_empty_cell_is_ignored():
    board = Board(3, 3)
    make_engine(board).request_jump(Position(1, 1))  # nothing there -> no error


def test_a_moving_piece_cannot_jump():
    board = rook_board()
    engine = make_engine(board)
    engine.request_move(Position(0, 0), Position(0, 2))  # rook is now MOVING
    engine.request_jump(Position(0, 0))                  # ignored
    assert board.piece_at(Position(0, 0)).state is PieceState.MOVING


def test_no_jump_after_game_over():
    board = Board(2, 3)
    board.place(Position(0, 0), Piece(PieceType("R", "rook"), Color.WHITE))
    board.place(Position(0, 2), Piece(PieceType("K", "king", is_king=True), Color.BLACK))
    black_rook = Piece(PieceType("R", "rook"), Color.BLACK)
    board.place(Position(1, 0), black_rook)
    engine = make_engine(board)
    engine.request_move(Position(0, 0), Position(0, 2))  # capture the king
    engine.wait(2000)                                    # -> game over
    engine.request_jump(Position(1, 0))                  # ignored
    assert black_rook.state is PieceState.IDLE
