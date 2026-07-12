from kfchess.model.board import Board
from kfchess.model.color import Color
from kfchess.model.piece import Piece
from kfchess.model.piece_type import PieceType
from kfchess.model.position import Position
from kfchess.movement.primitives import OffsetMovement, PawnMovement, SlideMovement
from kfchess.movement.rules import (
    ALL_DIRECTIONS,
    DIAGONAL,
    KNIGHT_OFFSETS,
    ORTHOGONAL,
    PAWN_FORWARD,
)

# Colour-independent primitives (slide/offset) ignore the mover; any piece works.
MOVER = Piece(PieceType("R", "x"), Color.WHITE)
BOARD = Board(8, 8)


def reach(movement, src, dst):
    return movement.can_reach(MOVER, Position(*src), Position(*dst), BOARD)


def put(board, at, color=Color.WHITE, letter="P"):
    board.place(Position(*at), Piece(PieceType(letter, "x"), color))


# --- SlideMovement / OffsetMovement shapes ---------------------------------


def test_rook_slides_orthogonally_any_distance():
    rook = SlideMovement(ORTHOGONAL)
    assert reach(rook, (0, 0), (0, 5))   # right (positive col)
    assert reach(rook, (5, 5), (5, 0))   # left (negative col)
    assert reach(rook, (5, 5), (0, 5))   # up (negative row)
    assert reach(rook, (0, 0), (3, 0))   # down (positive row)
    assert not reach(rook, (0, 0), (1, 1))  # diagonal not allowed


def test_slide_rejects_non_move():
    assert not reach(SlideMovement(ORTHOGONAL), (2, 2), (2, 2))


def test_bishop_slides_diagonally_only():
    bishop = SlideMovement(DIAGONAL)
    assert reach(bishop, (0, 0), (3, 3))
    assert reach(bishop, (3, 3), (0, 0))
    assert reach(bishop, (0, 4), (2, 2))
    assert not reach(bishop, (0, 0), (0, 2))


def test_queen_rejects_non_colinear_delta():
    queen = SlideMovement(ALL_DIRECTIONS)
    assert reach(queen, (0, 0), (0, 3))
    assert reach(queen, (0, 0), (3, 3))
    assert not reach(queen, (0, 0), (2, 1))


def test_king_moves_exactly_one_step():
    king = SlideMovement(ALL_DIRECTIONS, max_distance=1)
    assert reach(king, (1, 1), (0, 0))
    assert reach(king, (1, 1), (1, 2))
    assert not reach(king, (0, 0), (2, 2))
    assert not reach(king, (0, 0), (0, 2))


def test_knight_jumps_to_l_offsets_only():
    knight = OffsetMovement(KNIGHT_OFFSETS)
    assert reach(knight, (2, 2), (0, 1))
    assert reach(knight, (2, 2), (4, 3))
    assert not reach(knight, (2, 2), (2, 3))
    assert not reach(knight, (2, 2), (4, 4))


# --- blockers --------------------------------------------------------------


def test_slide_is_blocked_by_a_piece_in_the_path():
    board = Board(1, 4)
    put(board, (0, 1))
    assert not SlideMovement(ORTHOGONAL).can_reach(
        MOVER, Position(0, 0), Position(0, 3), board
    )


def test_slide_reaches_when_path_is_clear():
    assert SlideMovement(ORTHOGONAL).can_reach(
        MOVER, Position(0, 0), Position(0, 3), Board(1, 4)
    )


def test_slide_ignores_a_piece_on_the_destination_itself():
    board = Board(1, 4)
    put(board, (0, 3))
    assert SlideMovement(ORTHOGONAL).can_reach(
        MOVER, Position(0, 0), Position(0, 3), board
    )


def test_knight_ignores_blockers():
    board = Board(3, 3)
    put(board, (1, 1))
    assert OffsetMovement(KNIGHT_OFFSETS).can_reach(
        MOVER, Position(0, 0), Position(2, 1), board
    )


# --- PawnMovement ----------------------------------------------------------

WHITE_PAWN = Piece(PieceType("P", "x"), Color.WHITE)
BLACK_PAWN = Piece(PieceType("P", "x"), Color.BLACK)


def pawn():
    return PawnMovement(PAWN_FORWARD)


def test_white_pawn_moves_one_step_up_into_empty():
    assert pawn().can_reach(WHITE_PAWN, Position(1, 1), Position(0, 1), Board(3, 3))


def test_pawn_cannot_advance_onto_an_occupied_cell():
    board = Board(3, 3)
    put(board, (0, 1), color=Color.BLACK)  # enemy directly ahead
    assert not pawn().can_reach(WHITE_PAWN, Position(1, 1), Position(0, 1), board)


def test_pawn_captures_an_enemy_diagonally_forward():
    board = Board(3, 3)
    put(board, (0, 0), color=Color.BLACK)
    assert pawn().can_reach(WHITE_PAWN, Position(1, 1), Position(0, 0), board)


def test_pawn_cannot_move_diagonally_into_empty():
    assert not pawn().can_reach(WHITE_PAWN, Position(1, 1), Position(0, 0), Board(3, 3))


def test_pawn_cannot_capture_its_own_color_diagonally():
    board = Board(3, 3)
    put(board, (0, 0), color=Color.WHITE)  # friendly diagonal
    assert not pawn().can_reach(WHITE_PAWN, Position(1, 1), Position(0, 0), board)


def test_pawn_cannot_move_sideways_or_backward():
    board = Board(3, 3)
    assert not pawn().can_reach(WHITE_PAWN, Position(1, 1), Position(1, 2), board)  # side
    assert not pawn().can_reach(WHITE_PAWN, Position(1, 1), Position(2, 1), board)  # back


def test_black_pawn_advances_downward():
    board = Board(3, 3)
    assert pawn().can_reach(BLACK_PAWN, Position(0, 1), Position(1, 1), board)
    assert not pawn().can_reach(BLACK_PAWN, Position(1, 1), Position(0, 1), board)


def test_white_pawn_double_from_start_row():
    board = Board(5, 3)  # white start row = rows - 2 = 3
    assert pawn().can_reach(WHITE_PAWN, Position(3, 1), Position(1, 1), board)


def test_black_pawn_double_from_start_row():
    board = Board(5, 3)  # black start row = 1
    assert pawn().can_reach(BLACK_PAWN, Position(1, 1), Position(3, 1), board)


def test_pawn_double_from_non_start_row_is_rejected():
    board = Board(4, 3)  # white start row = 2; the pawn sits on row 3
    assert not pawn().can_reach(WHITE_PAWN, Position(3, 1), Position(1, 1), board)


def test_pawn_double_blocked_in_the_middle_is_rejected():
    board = Board(5, 3)
    put(board, (2, 1), color=Color.BLACK)  # blocker on the intermediate cell
    assert not pawn().can_reach(WHITE_PAWN, Position(3, 1), Position(1, 1), board)


def test_pawn_double_onto_an_occupied_destination_is_rejected():
    board = Board(5, 3)
    put(board, (1, 1), color=Color.BLACK)  # destination occupied
    assert not pawn().can_reach(WHITE_PAWN, Position(3, 1), Position(1, 1), board)


def test_pawn_cannot_double_diagonally():
    board = Board(5, 3)  # two rows AND a column change
    assert not pawn().can_reach(WHITE_PAWN, Position(3, 1), Position(1, 2), board)
