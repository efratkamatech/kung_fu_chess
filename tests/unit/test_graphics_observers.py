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
        self.settles = []
        self.captures = []
        self.cooldowns_done = []
        self.winners = []

    def on_move_started(self, piece, source, target, start_ms, arrival_ms):
        self.moves.append((piece, source, target, start_ms, arrival_ms))

    def on_settled(self, piece, cell, at_ms, cooldown_ms):
        self.settles.append((piece, cell, at_ms, cooldown_ms))

    def on_capture(self, victim, at_ms):
        self.captures.append((victim, at_ms))

    def on_cooldown_done(self, piece, at_ms):
        self.cooldowns_done.append((piece, at_ms))

    def on_game_over(self, winner):
        self.winners.append(winner)


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
    # A 2-cell move at MS_PER_CELL: announced as leaving at 0 and due at 2000, so a
    # listener on the far side can place it on every frame in between.
    assert spy.moves[0][3:] == (0, 2000)

    engine.wait(100000)                                  # rook arrives, captures the king
    assert len(spy.captures) == 1
    assert spy.captures[0][1] == 2000                    # stamped with the true arrival
    assert spy.winners == [Color.WHITE]                  # the winner rides the event
    assert engine.winner is Color.WHITE


def test_settling_and_the_end_of_a_cooldown_reach_observers():
    """Every change to the board is announced — the two that used to be silent too."""
    engine, _ = rook_then_king()
    spy = Spy()
    engine.add_observer(spy)
    rook = engine.board.piece_at(Position(2, 0))

    engine.request_move(Position(2, 0), Position(1, 0))  # 1 cell -> arrives at 1000
    engine.wait(1000)
    assert spy.settles == [(rook, Position(1, 0), 1000, 1000)]  # COOLDOWN_MS
    assert spy.cooldowns_done == []                             # still cooling

    engine.wait(1000)
    assert spy.cooldowns_done == [(rook, 2000)]  # its own ready time, not the tick


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
