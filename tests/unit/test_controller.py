from kfchess.config import COOLDOWN_MS, JUMP_DURATION_MS, MS_PER_CELL
from kfchess.control.controller import ClickOutcome, Controller
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

BIG_WAIT = 100000  # enough to complete any move on these small boards
PROMOTION = Promotion(PAWN_FORWARD, PieceType("Q", "queen"))


def piece(color=Color.WHITE, letter="K"):
    return Piece(PieceType(letter, "x"), color)


def setup(board):
    engine = GameEngine(
        board,
        Clock(),
        RuleEngine(standard_movement_rules()),
        RealTimeArbiter(board, MS_PER_CELL, PROMOTION, JUMP_DURATION_MS, COOLDOWN_MS),
    )
    return board, Controller(engine), engine


def test_select_then_move_via_center_clicks():
    board, controller, engine = setup(Board(3, 3))
    board.place(Position(0, 0), piece())
    controller.click(50, 50)     # center of (0,0) -> select
    controller.click(150, 150)   # center of (1,1) empty -> move request
    engine.wait(BIG_WAIT)        # let the timed motion complete
    assert board.is_empty(Position(0, 0))
    assert board.piece_at(Position(1, 1)) is not None


def test_off_board_click_is_ignored():
    board, controller, engine = setup(Board(2, 2))
    board.place(Position(0, 0), piece())
    controller.click(9999, 9999)  # far outside -> ignored (no selection)
    controller.click(150, 150)    # empty cell, still no selection -> ignored
    engine.wait(BIG_WAIT)
    assert board.piece_at(Position(0, 0)) is not None


def test_click_empty_with_no_selection_is_ignored():
    board, controller, engine = setup(Board(2, 2))
    controller.click(50, 50)      # empty, nothing selected
    controller.click(150, 150)    # empty, still nothing selected
    engine.wait(BIG_WAIT)
    assert board.is_empty(Position(0, 0))
    assert board.is_empty(Position(1, 1))


def test_clicking_a_friendly_piece_replaces_the_selection():
    board, controller, engine = setup(Board(1, 3))
    a = piece(Color.WHITE, "K")
    b = piece(Color.WHITE, "R")
    board.place(Position(0, 0), a)
    board.place(Position(0, 1), b)
    controller.click(50, 50)    # select a at (0,0)
    controller.click(150, 50)   # friendly b at (0,1) -> selection switches to b
    controller.click(250, 50)   # empty (0,2) -> the *selected* (b) moves there
    engine.wait(BIG_WAIT)
    assert board.piece_at(Position(0, 0)) is a   # a never moved
    assert board.is_empty(Position(0, 1))        # b left its cell
    assert board.piece_at(Position(0, 2)) is b   # b arrived


def test_move_onto_enemy_relocates_over_it():
    board, controller, engine = setup(Board(1, 2))
    white = piece(Color.WHITE)
    black = piece(Color.BLACK)
    board.place(Position(0, 0), white)
    board.place(Position(0, 1), black)
    controller.click(50, 50)    # select white
    controller.click(150, 50)   # enemy cell -> move request (capture)
    engine.wait(BIG_WAIT)
    assert board.is_empty(Position(0, 0))
    assert board.piece_at(Position(0, 1)) is white


def test_selection_is_dropped_when_its_piece_is_captured_under_it():
    # Real-time: after selecting a piece, an enemy captures it and stands on its
    # cell before the second click. That second click must NOT move the enemy piece
    # that now sits there — it should be read as a fresh selection of the clicked
    # friendly piece instead.
    board, controller, engine = setup(Board(1, 4))
    white = piece(Color.WHITE, "K")   # selected, then captured
    other = piece(Color.WHITE, "R")   # clicked after the capture
    enemy = piece(Color.BLACK, "R")   # captures `white`, then stands on its cell
    board.place(Position(0, 1), white)
    board.place(Position(0, 3), other)
    board.place(Position(0, 0), enemy)

    controller.click(150, 50)                          # select white at (0,1)
    engine.request_move(Position(0, 0), Position(0, 1))  # enemy moves to capture it
    engine.wait(BIG_WAIT)                              # capture completes; enemy on (0,1)

    controller.click(350, 50)   # click `other` at (0,3) -> fresh selection (not a move)
    controller.click(250, 50)   # empty (0,2) -> the *newly selected* `other` moves there
    engine.wait(BIG_WAIT)

    assert board.piece_at(Position(0, 1)) is enemy   # enemy was never moved
    assert board.piece_at(Position(0, 2)) is other   # `other` moved as the live selection
    assert board.is_empty(Position(0, 3))            # `other` left its origin


def test_selection_is_dropped_when_its_cell_becomes_empty():
    # If the selected piece leaves its cell (finishes an in-flight move) the cell is
    # empty on the next click. The click must be read fresh, not crash on a missing
    # selected piece.
    board, controller, engine = setup(Board(1, 3))
    white = piece(Color.WHITE, "K")   # selected, then vacates its cell
    other = piece(Color.WHITE, "R")   # clicked after the cell is empty
    board.place(Position(0, 1), white)

    controller.click(150, 50)                          # select white at (0,1)
    engine.request_move(Position(0, 1), Position(0, 2))  # it moves off (0,1)
    engine.wait(BIG_WAIT)                              # (0,1) is now empty
    board.place(Position(0, 0), other)

    controller.click(50, 50)    # click `other` at (0,0) -> fresh selection (no crash)
    controller.click(150, 50)   # empty (0,1) -> the newly selected `other` moves there
    engine.wait(BIG_WAIT)

    assert board.piece_at(Position(0, 1)) is other   # `other` was the live selection
    assert board.is_empty(Position(0, 0))            # `other` left its origin


def test_jump_makes_the_clicked_piece_jump():
    board, controller, _ = setup(Board(3, 3))
    p = piece()
    board.place(Position(1, 1), p)
    controller.jump(150, 150)  # center of (1,1)
    assert p.state is PieceState.JUMPING


def test_off_board_jump_is_ignored():
    board, controller, _ = setup(Board(2, 2))
    p = piece()
    board.place(Position(0, 0), p)
    controller.jump(9999, 9999)  # off board -> ignored
    assert p.state is PieceState.IDLE


def test_selected_cell_tracks_selection_and_deselect():
    board, controller, _ = setup(Board(2, 2))
    board.place(Position(0, 0), piece())
    assert controller.selected_cell is None
    controller.click(50, 50)                      # select (0,0)
    assert controller.selected_cell == Position(0, 0)
    controller.deselect()
    assert controller.selected_cell is None


def test_click_reports_each_outcome():
    board, controller, _ = setup(Board(1, 3))
    board.place(Position(0, 0), piece(Color.WHITE, "R"))
    assert controller.click(9999, 9999) is ClickOutcome.IGNORED   # off the board
    assert controller.click(150, 50) is ClickOutcome.IGNORED      # empty, nothing selected
    assert controller.click(50, 50) is ClickOutcome.SELECTED      # select the rook
    assert controller.click(250, 50) is ClickOutcome.MOVED        # (0,2) is legal for a rook


def test_click_reports_an_illegal_move():
    board, controller, _ = setup(Board(3, 3))
    board.place(Position(0, 0), piece(Color.WHITE, "K"))
    controller.click(50, 50)                                     # select the king (0,0)
    assert controller.click(250, 250) is ClickOutcome.ILLEGAL    # (2,2) is too far for a king
