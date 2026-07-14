from kfchess.engine.arbiter import Motion, MovingPiece, RealTimeArbiter
from kfchess.model.board import Board
from kfchess.model.color import Color
from kfchess.model.piece import Piece, PieceState
from kfchess.model.piece_type import PieceType
from kfchess.model.position import Position
from kfchess.movement.rules import PAWN_FORWARD
from kfchess.rules.promotion import Promotion

MS_PER_CELL = 1000
JUMP_DURATION_MS = 1000
COOLDOWN_MS = 1000
PROMOTION = Promotion(PAWN_FORWARD, PieceType("Q", "queen"))


def make_arbiter(board, cooldown_ms=COOLDOWN_MS):
    return RealTimeArbiter(
        board, MS_PER_CELL, PROMOTION, JUMP_DURATION_MS, cooldown_ms
    )


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


def test_motion_position_at_interpolates_and_clamps():
    # A 2-cell move from (0,0) to (0,2) over [0, 2000].
    motion = Motion(rook(), Position(0, 0), Position(0, 2), 0, 2000, 0)
    assert motion.position_at(0) == (0.0, 0.0)       # at the start -> source
    assert motion.position_at(1000) == (0.0, 1.0)    # halfway -> between the cells
    assert motion.position_at(2000) == (0.0, 2.0)    # at arrival -> target
    assert motion.position_at(-500) == (0.0, 0.0)    # before start -> clamped to source
    assert motion.position_at(9999) == (0.0, 2.0)    # past arrival -> clamped to target


def test_motion_position_at_handles_a_diagonal():
    motion = Motion(rook(), Position(0, 0), Position(2, 2), 0, 2000, 0)
    assert motion.position_at(500) == (0.5, 0.5)     # quarter of the way along both axes


def test_cell_timeline_steps_through_a_slide_with_half_open_windows():
    motion = Motion(rook(), Position(0, 0), Position(0, 3), 0, 3000, 0)
    assert motion.cell_timeline() == [
        (Position(0, 0), 0, 1000),
        (Position(0, 1), 1000, 2000),
        (Position(0, 2), 2000, 3000),
        (Position(0, 3), 3000, 4000),
    ]


def test_cell_timeline_of_a_knight_jump_has_no_cells_in_between():
    motion = Motion(rook(), Position(0, 0), Position(2, 1), 0, 2000, 0)  # non-straight
    assert motion.cell_timeline() == [
        (Position(0, 0), 0, 2000),
        (Position(2, 1), 2000, 4000),
    ]


def test_moving_pieces_reports_in_flight_positions():
    board = board_with_rook()
    piece = board.piece_at(Position(0, 0))
    arbiter = make_arbiter(board)
    assert arbiter.moving_pieces(0) == []            # nothing in flight yet
    arbiter.start_motion(piece, Position(0, 0), Position(0, 2), now_ms=0)

    snapshot = arbiter.moving_pieces(1000)           # halfway there
    assert snapshot == [
        MovingPiece(piece, (0.0, 1.0), Position(0, 0), Position(0, 2))
    ]

    arbiter.resolve(2000)                            # it arrives and leaves flight
    assert arbiter.moving_pieces(2000) == []


def test_start_motion_keeps_piece_at_origin_and_marks_it_moving():
    board = board_with_rook()
    piece = board.piece_at(Position(0, 0))
    make_arbiter(board).start_motion(
        piece, Position(0, 0), Position(0, 2), now_ms=0
    )
    assert board.piece_at(Position(0, 0)) is piece  # still at origin
    assert piece.state is PieceState.MOVING


def test_resolve_before_arrival_does_nothing():
    board = board_with_rook()
    piece = board.piece_at(Position(0, 0))
    arbiter = make_arbiter(board)
    arbiter.start_motion(piece, Position(0, 0), Position(0, 2), now_ms=0)  # arrives 2000
    arbiter.resolve(1000)  # too early
    assert board.piece_at(Position(0, 0)) is piece
    assert board.is_empty(Position(0, 2))
    assert piece.state is PieceState.MOVING


def test_resolve_at_arrival_relocates_and_puts_the_piece_on_cooldown():
    board = board_with_rook()
    piece = board.piece_at(Position(0, 0))
    arbiter = make_arbiter(board)
    arbiter.start_motion(piece, Position(0, 0), Position(0, 2), now_ms=0)
    arbiter.resolve(2000)
    assert board.is_empty(Position(0, 0))
    assert board.piece_at(Position(0, 2)) is piece
    assert piece.state is PieceState.COOLDOWN  # just landed, not free yet
    arbiter.resolve(3000)  # cooldown (2000 + 1000) has now elapsed
    assert piece.state is PieceState.IDLE


def test_cooldown_of_zero_lands_straight_to_idle():
    board = board_with_rook()
    piece = board.piece_at(Position(0, 0))
    arbiter = make_arbiter(board, cooldown_ms=0)
    arbiter.start_motion(piece, Position(0, 0), Position(0, 2), now_ms=0)
    arbiter.resolve(2000)
    assert piece.state is PieceState.IDLE  # no cooldown -> free in the same pass


def test_arriving_piece_captures_a_settled_piece_at_the_destination():
    board = Board(1, 3)
    mover = rook(Color.WHITE)
    board.place(Position(0, 0), mover)
    board.place(Position(0, 2), rook(Color.BLACK))  # enemy settled on the destination
    arbiter = make_arbiter(board)
    arbiter.start_motion(mover, Position(0, 0), Position(0, 2), now_ms=0)
    arbiter.resolve(2000)
    assert board.piece_at(Position(0, 2)) is mover  # captured
    assert not arbiter.is_game_over  # capturing a non-king does not end the game


def king(color=Color.BLACK):
    return Piece(PieceType("K", "king", is_king=True), color)


def test_capturing_a_king_ends_the_game():
    board = Board(1, 3)
    white = rook(Color.WHITE)
    board.place(Position(0, 0), white)
    board.place(Position(0, 2), king(Color.BLACK))
    arbiter = make_arbiter(board)
    assert not arbiter.is_game_over
    arbiter.start_motion(white, Position(0, 0), Position(0, 2), now_ms=0)
    arbiter.resolve(2000)
    assert arbiter.is_game_over


def test_two_enemies_crossing_the_one_that_started_first_wins():
    board = Board(1, 4)
    white = rook(Color.WHITE)
    black = rook(Color.BLACK)
    board.place(Position(0, 0), white)
    board.place(Position(0, 3), black)
    arbiter = make_arbiter(board)
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
    arbiter = make_arbiter(board)
    arbiter.start_motion(black, Position(0, 3), Position(0, 0), now_ms=0)  # arrives 3000
    arbiter.start_motion(white, Position(0, 2), Position(0, 3), now_ms=0)  # arrives 1000
    arbiter.resolve(1000)  # white reaches black's cell first and captures it
    assert board.piece_at(Position(0, 3)) is white
    arbiter.resolve(3000)  # black's motion was cancelled, so nothing reappears
    assert board.piece_at(Position(0, 3)) is white
    assert board.is_empty(Position(0, 0))


def test_enemies_meeting_midpath_the_later_entrant_eats_and_continues():
    # A white rook slides up column 2; a black rook slides along row 2. They meet on
    # cell (2,2). Black enters it later, so black eats white and keeps going to (2,4).
    board = Board(5, 5)
    white = rook(Color.WHITE)
    black = rook(Color.BLACK)
    board.place(Position(4, 2), white)
    board.place(Position(2, 0), black)
    arbiter = make_arbiter(board)
    arbiter.start_motion(white, Position(4, 2), Position(0, 2), now_ms=0)    # (2,2) at 2000
    arbiter.start_motion(black, Position(2, 0), Position(2, 4), now_ms=500)  # (2,2) at 2500
    arbiter.resolve(3000)  # they have met on (2,2); black (later) ate white

    assert board.is_empty(Position(4, 2))  # white removed from its origin, eaten mid-path
    arbiter.resolve(4500)  # black finishes its move
    assert board.piece_at(Position(2, 4)) is black  # the winner continued to its target
    assert board.is_empty(Position(2, 2))  # nobody settled on the meeting cell


def test_midpath_tie_is_won_by_the_piece_that_started_first():
    # Both rooks enter (2,2) at the same instant. White started first, so white eats
    # black and continues to (0,2).
    board = Board(5, 5)
    white = rook(Color.WHITE)
    black = rook(Color.BLACK)
    board.place(Position(4, 2), white)
    board.place(Position(2, 0), black)
    arbiter = make_arbiter(board)
    arbiter.start_motion(white, Position(4, 2), Position(0, 2), now_ms=0)  # started first
    arbiter.start_motion(black, Position(2, 0), Position(2, 4), now_ms=0)  # both reach (2,2) at 2000
    arbiter.resolve(4000)

    assert board.piece_at(Position(0, 2)) is white  # white survived and reached its target
    assert board.is_empty(Position(2, 0))  # black removed from its origin, eaten
    assert board.is_empty(Position(2, 4))  # black never reached its target


def test_friend_met_midpath_stops_one_cell_short_while_the_other_continues():
    # Two white rooks cross on cell (2,2). The horizontal one enters it first; the
    # vertical one arrives later, cannot capture a friend, and stops at (3,2) — the
    # cell just before the meeting cell on its path. The first rook continues.
    board = Board(5, 5)
    horizontal = rook(Color.WHITE)
    vertical = rook(Color.WHITE)
    board.place(Position(2, 0), horizontal)
    board.place(Position(4, 2), vertical)
    arbiter = make_arbiter(board)
    arbiter.start_motion(horizontal, Position(2, 0), Position(2, 4), now_ms=0)   # (2,2) at 2000
    arbiter.start_motion(vertical, Position(4, 2), Position(0, 2), now_ms=500)   # (2,2) at 2500
    arbiter.resolve(4500)

    assert board.piece_at(Position(3, 2)) is vertical  # stopped one cell short
    assert vertical.state is PieceState.IDLE           # landed and cooled down by now
    assert board.piece_at(Position(2, 4)) is horizontal  # the other reached its target
    assert board.is_empty(Position(0, 2))              # the blocked rook never got there
    assert board.is_empty(Position(2, 2))              # nobody settled on the meeting cell


def test_arriving_pawn_on_its_far_row_is_promoted():
    board = Board(2, 3)
    pawn = Piece(PieceType("P", "pawn", is_pawn=True), Color.WHITE)
    board.place(Position(1, 1), pawn)
    arbiter = make_arbiter(board)
    arbiter.start_motion(pawn, Position(1, 1), Position(0, 1), now_ms=0)  # white forward
    arbiter.resolve(1000)
    assert board.piece_at(Position(0, 1)).piece_type.letter == "Q"


def test_jump_lands_in_place_when_no_one_arrives():
    board = Board(1, 3)
    piece = rook(Color.WHITE)
    board.place(Position(0, 1), piece)
    arbiter = make_arbiter(board)
    arbiter.start_jump(piece, Position(0, 1), now_ms=0)  # airborne until 1000
    assert piece.state is PieceState.JUMPING
    arbiter.resolve(500)  # still airborne (before the window ends)
    assert piece.state is PieceState.JUMPING
    arbiter.resolve(1000)  # window ends -> lands, unmoved
    assert piece.state is PieceState.IDLE
    assert board.piece_at(Position(0, 1)) is piece


def test_airborne_piece_captures_an_arriving_enemy():
    board = Board(1, 3)
    jumper = rook(Color.WHITE)
    attacker = rook(Color.BLACK)
    board.place(Position(0, 0), jumper)
    board.place(Position(0, 1), attacker)
    arbiter = make_arbiter(board)
    arbiter.start_jump(jumper, Position(0, 0), now_ms=0)  # airborne until 1000
    arbiter.start_motion(attacker, Position(0, 1), Position(0, 0), now_ms=0)  # arrives 1000
    arbiter.resolve(1000)  # arrives exactly as the jump ends -> jumper captures it
    assert board.piece_at(Position(0, 0)) is jumper
    assert board.is_empty(Position(0, 1))
    assert jumper.state is PieceState.IDLE


def test_enemy_arriving_after_the_window_captures_normally():
    board = Board(1, 3)
    jumper = rook(Color.WHITE)
    attacker = rook(Color.BLACK)
    board.place(Position(0, 0), jumper)
    board.place(Position(0, 2), attacker)
    arbiter = make_arbiter(board)
    arbiter.start_jump(jumper, Position(0, 0), now_ms=0)  # airborne until 1000
    arbiter.start_motion(attacker, Position(0, 2), Position(0, 0), now_ms=0)  # arrives 2000
    arbiter.resolve(2000)  # 2000 > jump end 1000 -> normal capture of the (landed) jumper
    assert board.piece_at(Position(0, 0)) is attacker


def test_airborne_defender_ignores_a_friendly_arriver():
    board = Board(1, 3)
    jumper = rook(Color.WHITE)
    friend = rook(Color.WHITE)
    board.place(Position(0, 0), jumper)
    board.place(Position(0, 1), friend)
    arbiter = make_arbiter(board)
    arbiter.start_jump(jumper, Position(0, 0), now_ms=0)
    arbiter.start_motion(friend, Position(0, 1), Position(0, 0), now_ms=0)  # arrives 1000
    arbiter.resolve(1000)  # same colour -> not an airborne capture; normal resolution
    assert board.piece_at(Position(0, 0)) is friend


def test_airborne_defender_only_matches_its_own_cell():
    board = Board(1, 3)
    jumper = rook(Color.WHITE)
    attacker = rook(Color.BLACK)
    board.place(Position(0, 2), jumper)
    board.place(Position(0, 1), attacker)
    arbiter = make_arbiter(board)
    arbiter.start_jump(jumper, Position(0, 2), now_ms=0)  # jump on (0,2)
    arbiter.start_motion(attacker, Position(0, 1), Position(0, 0), now_ms=0)  # arrives at (0,0)
    arbiter.resolve(1000)  # attacker's cell differs from the jump cell -> normal move
    assert board.piece_at(Position(0, 0)) is attacker
    assert board.piece_at(Position(0, 2)) is jumper  # jumper landed, untouched
