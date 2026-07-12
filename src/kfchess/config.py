"""Central configuration: the text-fixture vocabulary and validation codes.

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

# --- Command names -----------------------------------------------------------
# Iteration 1 supports only `print board`; `click` and `wait` join in Iteration 2.
CMD_PRINT_BOARD = "print board"

# Color is encoded as a one-letter prefix on each piece token, e.g. "wK", "bR".
WHITE_PREFIX = "w"
BLACK_PREFIX = "b"

# --- Validation error codes (emitted verbatim on a malformed fixture) --------
ERR_MISSING_BOARD_SECTION = "MISSING_BOARD_SECTION"
ERR_MISSING_COMMANDS_SECTION = "MISSING_COMMANDS_SECTION"
ERR_UNKNOWN_COMMAND = "UNKNOWN_COMMAND"
# PROVISIONAL: emitted for a malformed board cell token (bad color prefix or
# unknown piece letter, e.g. "xK" / "wZ"). The exact token text is not yet
# confirmed against VPL — verify with a test and change this one line if needed.
ERR_INVALID_PIECE = "INVALID_PIECE"
