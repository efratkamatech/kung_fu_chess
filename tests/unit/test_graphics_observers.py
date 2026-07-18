"""Events, cooldown progress, and jump-cooldown, exercised through the real wiring
(build_game) that the graphics app uses — the paths the GUI depends on."""

from kfchess.app.bootstrap import build_game
from kfchess.engine.events import GameObserver
from kfchess.model.board import Board
from kfchess.model.color import Color
from kfchess.model.piece import Piece, PieceState
from kfchess.model.piece_type import standard_piece_types
from kfchess.model.position import Position


class Spy(GameObserver):
    def __init__(self):
        self.moves = []
        self.captures = []
        self.game_overs = 0

    def on_move_started(self, piece, source, target):
        self.moves.append((piece, source, target))

    def on_capture(self, victim):
        self.captures.append(victim)

    def on_game_over(self):
        self.game_overs += 1


def rook_then_king():
    reg = standard_piece_types()
    grid = [
        [Piece(reg.get("K"), Color.BLACK)],
        [None],
        [Piece(reg.get("R"), Color.WHITE)],
    ]
    return build_game(Board.from_grid(grid))


def test_move_capture_and_game_over_reach_registered_observers():
    engine, _ = rook_then_king()
    spy = Spy()
    engine.add_observer(spy)

    engine.request_move(Position(2, 0), Position(0, 0))  # white rook toward the king
    assert len(spy.moves) == 1                           # move-started fired

    engine.wait(100000)                                  # rook arrives, captures the king
    assert len(spy.captures) == 1
    assert spy.game_overs == 1
    assert engine.winner is Color.WHITE


def test_cooldown_progress_reports_a_just_landed_piece():
    reg = standard_piece_types()
    grid = [[None], [None], [Piece(reg.get("R"), Color.WHITE)]]
    engine, _ = build_game(Board.from_grid(grid))

    engine.request_move(Position(2, 0), Position(0, 0))  # 2 cells -> arrives at 2000
    engine.wait(2000)                                    # lands into cooldown

    progress = engine.cooldown_progress()
    assert len(progress) == 1
    (piece, fraction), = progress.items()
    assert piece.state is PieceState.COOLDOWN
    assert 0.0 <= fraction <= 1.0


def test_a_jump_lands_into_its_own_low_cooldown():
    reg = standard_piece_types()
    engine, _ = build_game(Board.from_grid([[Piece(reg.get("K"), Color.WHITE)]]))
    piece = engine.board.piece_at(Position(0, 0))

    engine.request_jump(Position(0, 0))
    engine.wait(2000)                       # JUMP_DURATION_MS -> airborne window ends, lands
    assert piece.state is PieceState.COOLDOWN
    assert engine.cooldown_progress()       # the low jump-cooldown is active

    engine.wait(500)                        # JUMP_COOLDOWN_MS (400) elapses
    assert piece.state is PieceState.IDLE
    assert engine.cooldown_progress() == {}
