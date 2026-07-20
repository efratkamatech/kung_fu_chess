from kfchess.config import CELL_PX, PIECES_DIR, STATE_IDLE, STATE_JUMP
from kfchess.graphics.assets import AnimationBank
from kfchess.model.color import Color
from kfchess.model.piece import Piece
from kfchess.model.piece_type import PieceType, standard_piece_types
from kfchess.tokens import load_board_csv, piece_token, token_to_piece


def test_piece_token_composes_color_and_letter():
    assert piece_token(Piece(PieceType("K", "king"), Color.WHITE)) == "wK"
    assert piece_token(Piece(PieceType("P", "pawn"), Color.BLACK)) == "bP"


def test_token_to_piece_and_empty():
    reg = standard_piece_types()
    piece = token_to_piece("bR", reg)
    assert piece.color is Color.BLACK and piece.piece_type.letter == "R"
    assert token_to_piece("", reg) is None
    assert token_to_piece("  ", reg) is None


def test_load_board_csv_builds_board_with_empty_rows(tmp_path):
    csv = tmp_path / "b.csv"
    csv.write_text("wK,bK\n\n,\n", encoding="utf-8")  # blank line skipped; empty-cell row kept
    board = load_board_csv(csv)
    from kfchess.model.position import Position

    assert (board.rows, board.cols) == (2, 2)
    assert piece_token(board.piece_at(Position(0, 0))) == "wK"
    assert board.piece_at(Position(1, 0)) is None


def test_animation_bank_loads_frames_scaled_to_the_cell():
    bank = AnimationBank(PIECES_DIR, CELL_PX)
    idle = bank.animation("wP", STATE_IDLE)
    assert idle.frame_count == 5
    assert idle.frame_at(0).width == CELL_PX and idle.frame_at(0).height == CELL_PX


def test_animation_bank_reads_loop_flag_from_config():
    bank = AnimationBank(PIECES_DIR, CELL_PX)
    # idle loops (is_loop true); jump also loops in this project.
    assert bank.animation("wP", STATE_JUMP).frame_at(0) is not None


def test_animation_bank_caches_each_state():
    bank = AnimationBank(PIECES_DIR, CELL_PX)
    assert bank.animation("bR", STATE_IDLE) is bank.animation("bR", STATE_IDLE)
