"""Central configuration: the text-fixture vocabulary, validation codes, and asset paths.

Business logic must never hardcode these tokens. Every layer imports them from
here so the wire/text format lives in exactly one place — critical because VPL
compares program output byte-for-byte, and any format tweak should be a one-line
change here rather than a hunt through the codebase.

Fixture shape (Iteration 1):

    Board:
    wK . . bK
    . . . .
    wR . . bR
    Commands:
    print board

- A ``Board:`` section: rows of space-separated cells; ``.`` is an empty cell;
  a piece is a color prefix (``w``/``b``) + an uppercase type letter (e.g. ``wK``).
- A ``Commands:`` section: one command per line.
"""

# --- Fixture section headers -------------------------------------------------
BOARD_SECTION_HEADER = "Board:"
COMMANDS_SECTION_HEADER = "Commands:"

# --- Board cell vocabulary ---------------------------------------------------
EMPTY_CELL = "."
CELL_SEPARATOR = " "  # single space between cells within a row

# --- Geometry ----------------------------------------------------------------
# Each board cell is CELL_PX x CELL_PX pixels; a click at pixel (x, y) maps to the
# cell (row = y // CELL_PX, col = x // CELL_PX).
CELL_PX = 100

# --- Timing ------------------------------------------------------------------
# A move takes this long per cell of travel: a move of `distance` cells arrives
# `distance * MS_PER_CELL` ms after it starts (so a 2-cell move takes 2000 ms).
MS_PER_CELL = 1000
# A jump keeps a piece airborne in place for this long.
JUMP_DURATION_MS = 1000
# After a piece lands from a move it is on cooldown for this long: it cannot start
# a new move until the cooldown elapses. Set to 0 to disable cooldown entirely.
COOLDOWN_MS = 1000

# --- Command names -----------------------------------------------------------
CMD_PRINT_BOARD = "print board"
CMD_CLICK = "click"  # usage: "click <x> <y>"
CMD_WAIT = "wait"    # usage: "wait <ms>"
CMD_JUMP = "jump"    # usage: "jump <x> <y>"

# Color is encoded as a one-letter prefix on each piece token, e.g. "wK", "bR".
WHITE_PREFIX = "w"
BLACK_PREFIX = "b"

# --- Validation error codes --------------------------------------------------
# VPL prints validation errors as "ERROR <CODE>" (confirmed by the grader for
# UNKNOWN_TOKEN and ROW_WIDTH_MISMATCH). Codes are stored bare; error_message()
# applies the prefix at the single place errors are emitted, so the format is
# defined once.
ERROR_PREFIX = "ERROR "

# Confirmed against VPL:
ERR_UNKNOWN_TOKEN = "UNKNOWN_TOKEN"             # malformed board cell (bad prefix/letter)
ERR_ROW_WIDTH_MISMATCH = "ROW_WIDTH_MISMATCH"   # board rows of unequal width
# Names match the assignment, but exact output not yet confirmed against VPL:
ERR_MISSING_BOARD_SECTION = "MISSING_BOARD_SECTION"
ERR_MISSING_COMMANDS_SECTION = "MISSING_COMMANDS_SECTION"
ERR_UNKNOWN_COMMAND = "UNKNOWN_COMMAND"


def error_message(code: str) -> str:
    """Format a validation code as the exact stdout line: ``ERROR <CODE>``."""
    return f"{ERROR_PREFIX}{code}"


# --- Graphics assets (used only by the graphics layer, never by the text core) --
# On-disk locations of the image assets, resolved relative to this file so the app
# runs from any working directory. The text/VPL path never touches these, so their
# absence on the grader (which uploads only main.py + src/) is harmless.
from pathlib import Path  # noqa: E402  (kept near the paths it supports)

ASSETS_DIR = Path(__file__).resolve().parents[2] / "assets"
BOARD_IMAGE = ASSETS_DIR / "board.png"   # board background image
BOARD_CSV = ASSETS_DIR / "board.csv"     # starting position, one comma-separated row per line
PIECES_DIR = ASSETS_DIR / "pieces_mine"  # per-piece sprite folders, named by token (wK, bP, ...)

# Sprite state folder names (match the on-disk assets/pieces_mine/<token>/states/).
STATE_IDLE = "idle"
STATE_MOVE = "move"
STATE_JUMP = "jump"
STATE_SHORT_REST = "short_rest"
STATE_LONG_REST = "long_rest"
