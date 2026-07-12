from kfchess.model.board import Board
from kfchess.model.color import Color
from kfchess.model.piece import Piece
from kfchess.model.piece_type import PieceType
from kfchess.model.position import Position
from kfchess.movement.primitives import OffsetMovement, SlideMovement
from kfchess.movement.rules import ALL_DIRECTIONS, DIAGONAL, KNIGHT_OFFSETS, ORTHOGONAL

# For pure-shape tests an empty board suffices (nothing blocks the path).
BOARD = Board(8, 8)


def reach(movement, src, dst):
    return movement.can_reach(Position(*src), Position(*dst), BOARD)


def board_with_blocker(size, at):
    board = Board(*size)
    board.place(Position(*at), Piece(PieceType("P", "x"), Color.WHITE))
    return board


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
    assert reach(bishop, (0, 4), (2, 2))     # down-left
    assert not reach(bishop, (0, 0), (0, 2))  # straight not allowed


def test_queen_rejects_non_colinear_delta():
    queen = SlideMovement(ALL_DIRECTIONS)
    assert reach(queen, (0, 0), (0, 3))
    assert reach(queen, (0, 0), (3, 3))
    assert not reach(queen, (0, 0), (2, 1))  # crooked, not a straight line


def test_king_moves_exactly_one_step():
    king = SlideMovement(ALL_DIRECTIONS, max_distance=1)
    assert reach(king, (1, 1), (0, 0))       # one diagonal
    assert reach(king, (1, 1), (1, 2))       # one orthogonal
    assert not reach(king, (0, 0), (2, 2))   # two diagonal
    assert not reach(king, (0, 0), (0, 2))   # two straight


def test_knight_jumps_to_l_offsets_only():
    knight = OffsetMovement(KNIGHT_OFFSETS)
    assert reach(knight, (2, 2), (0, 1))     # offset (-2, -1)
    assert reach(knight, (2, 2), (4, 3))     # offset (2, 1)
    assert not reach(knight, (2, 2), (2, 3))  # adjacent, not an L
    assert not reach(knight, (2, 2), (4, 4))  # diagonal, not an L


def test_slide_is_blocked_by_a_piece_in_the_path():
    board = board_with_blocker((1, 4), at=(0, 1))  # blocker between source and target
    rook = SlideMovement(ORTHOGONAL)
    assert not rook.can_reach(Position(0, 0), Position(0, 3), board)


def test_slide_reaches_when_path_is_clear():
    rook = SlideMovement(ORTHOGONAL)
    assert rook.can_reach(Position(0, 0), Position(0, 3), Board(1, 4))


def test_slide_ignores_a_piece_on_the_destination_itself():
    # The destination occupant is the RuleEngine's concern, not the path check.
    board = board_with_blocker((1, 4), at=(0, 3))
    rook = SlideMovement(ORTHOGONAL)
    assert rook.can_reach(Position(0, 0), Position(0, 3), board)


def test_knight_ignores_blockers():
    board = board_with_blocker((3, 3), at=(1, 1))
    knight = OffsetMovement(KNIGHT_OFFSETS)
    assert knight.can_reach(Position(0, 0), Position(2, 1), board)  # jumps over
