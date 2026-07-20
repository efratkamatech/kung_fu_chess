import numpy as np

from kfchess.bus.event_bus import EventBus
from kfchess.bus.events import MoveStarted
from kfchess.graphics.events import MovesLog, ScoreBoard
from kfchess.graphics.hud import Hud
from kfchess.graphics.img import Img
from kfchess.model.color import Color
from kfchess.model.piece import Piece
from kfchess.model.piece_type import standard_piece_types
from kfchess.model.position import Position


def test_hud_draw_writes_name_score_and_moves_onto_the_canvas():
    bus = EventBus()
    log = MovesLog(board_rows=8)
    log.subscribe(bus)
    bus.publish(
        MoveStarted(
            Piece(standard_piece_types().get("N"), Color.WHITE),
            Position(7, 1),
            Position(5, 2),
        )
    )
    score = ScoreBoard()
    hud = Hud("Efrat", Color.WHITE, log, score, left_x=20)

    canvas = Img.blank(360, 800, 3, (20, 20, 20))
    before = canvas.img.copy()
    hud.draw(canvas)

    assert not np.array_equal(before, canvas.img)  # text (name / score / a move) was drawn
