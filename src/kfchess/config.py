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
# A jump keeps a piece airborne in place for this long, then a short cooldown
# follows before the piece can move again.
JUMP_DURATION_MS = 2000
JUMP_COOLDOWN_MS = 400
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
import os  # noqa: E402  (for the few settings that come from the environment)
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

# Fallback animation frame rate if a state's config.json omits ``frames_per_sec``.
FPS_DEFAULT = 8

# Colour (B, G, R) of the outline drawn around the currently selected cell.
SELECT_COLOR = (0, 255, 0)

# Legal-move hints: a translucent green fill on each cell the selected piece may reach.
LEGAL_MOVE_COLOR = (0, 220, 0)
LEGAL_MOVE_ALPHA = 0.30
# Illegal-target feedback: a red outline flashed on a cell the piece cannot reach.
INVALID_MOVE_COLOR = (0, 0, 255)
INVALID_FLASH_SECONDS = 0.4

# Cooldown gauge: a translucent yellow fill over a just-moved piece's cell that
# drains downward as its cooldown elapses.
COOLDOWN_COLOR = (0, 255, 255)   # yellow (B, G, R)
COOLDOWN_ALPHA = 0.45            # 0 = invisible, 1 = opaque

# --- HUD (the side panel with names, score, and the moves log) ---------------
PANEL_PX = 340                     # width in pixels of the side panel
PANEL_BG = (32, 32, 32)            # panel background colour (B, G, R)
HUD_TEXT_COLOR = (235, 235, 235)   # default text colour
HUD_MOVES_VISIBLE = 12             # how many recent moves the log shows
WHITE_PLAYER_NAME = "White"
BLACK_PLAYER_NAME = "Black"

# --- Game-over banner --------------------------------------------------------
GAMEOVER_BG = (0, 0, 0)            # dim overlay colour (B, G, R)
GAMEOVER_ALPHA = 0.6              # overlay opacity
GAMEOVER_TEXT_COLOR = (255, 255, 255)
# The start banner reuses the same overlay, but dims the board more lightly since the
# player is about to interact with it.
STARTBANNER_ALPHA = 0.35

# --- Networking (the WebSocket server) ---------------------------------------
# The interface the server binds. "localhost" keeps a run on a laptop private, which is
# the right default; a container has to bind 0.0.0.0 or nothing outside it can connect,
# so `docker-compose.yml` sets this. It is read from the environment because it is a
# property of *where the process runs*, not of the game.
SERVER_HOST = os.environ.get("KFC_SERVER_HOST", "localhost")
SERVER_PORT = 8765
# How often the server advances the game. ~20/sec keeps in-flight motion smooth, and
# it is the *ceiling* on how long the tick loop sleeps: a game with an event due sooner
# is woken for it, an idle game waits out the whole interval.
SERVER_TICK_MS = 50
# On top of the per-event deltas, every client is sent a full snapshot this often to
# correct any drift. Lower = more traffic, faster self-correction after a lost frame.
# This is the one periodic broadcast left; everything else is sent only when it happens.
SNAPSHOT_RESYNC_MS = 10_000
# Transport keepalive (liveness): the server sends a WebSocket ping this often and drops
# a connection that does not pong within the timeout. This is what notices a *silently*
# dropped client — a network that vanished without a close frame — and it fires the same
# disconnect path (and resign countdown) as a clean close. Tighter than the websockets
# library's ~20s defaults, so a dropped player is caught within ~20s rather than ~40s;
# an application-level heartbeat on top would only duplicate this.
WS_PING_INTERVAL_S = 10
WS_PING_TIMEOUT_S = 10

# --- The message bus between the gateway and the shard (S2) ------------------
# Where NATS is listening. Set from the environment because it is a property of the
# deployment, like DATABASE_URL below; docker-compose.yml points both services at the
# `nats` service, and a bare `localhost` is the right default for running them by hand.
NATS_URL = os.environ.get("NATS_URL", "nats://localhost:4222")
# Who this process is. A gateway's id prefixes every connection id it hands out, so the
# replies to its sockets are addressed to a subject only it is subscribed to; a shard's
# id names the subjects only it serves. They must be unique per replica, which is what
# the orchestrator is for -- these defaults are for a single machine.
GATEWAY_ID = os.environ.get("KFC_GATEWAY_ID", "gw1")
SHARD_ID = os.environ.get("KFC_SHARD_ID", "sh1")

# --- Accounts and rating (server-side) ---------------------------------------
# Where the users database lives (username, password hash, rating). Resolved at the
# repo root so it survives across server runs. (git-ignored; not game art.)
USERS_DB = ASSETS_DIR.parent / "users.db"
# A ``postgresql://`` DSN takes over when it is set: that is how the container is
# pointed at its database. Unset — a laptop, and every test — falls back to the SQLite
# file above, so nothing about a local run changes.
DATABASE_URL = os.environ.get("DATABASE_URL", "")
START_RATING = 1200   # every new account starts here
ELO_K = 32            # the ELO K-factor: the most a single game can move a rating

# --- Matchmaking (M5) --------------------------------------------------------
# Two seekers are paired only if their ratings differ by at most this much; among
# the candidates in range, the closest rating wins (ties go to the longest waiter).
MATCH_ELO_RANGE = 100
# A lone seeker waits at most this long before the client shows "can't find opponent".
MATCH_TIMEOUT_MS = 60_000

# --- Disconnect handling (M5) ------------------------------------------------
# When a player's socket drops mid-game, the opponent sees a countdown for this long;
# if they have not reconnected by the end, they auto-resign and the opponent wins.
RESIGN_COUNTDOWN_MS = 20_000

# --- Rooms (M6) --------------------------------------------------------------
# Crockford base32: the digits and uppercase letters with O, I, L and U removed, so an
# id read aloud or typed off a screenshot cannot be mistaken (no 0/O, no 1/I/L). Six
# characters give ~1.07e9 ids, comfortably more than the rooms that can be live at once.
ROOM_ID_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
ROOM_ID_LENGTH = 6
# How many times to redraw an id that is already taken before giving up. A collision is
# already vanishingly unlikely; this is the guard that turns "somehow, always taken"
# into a refusal the player sees, instead of a loop that spins for ever holding the
# server's only thread.
ROOM_ID_MAX_ATTEMPTS = 10

# --- Logging (M6) ------------------------------------------------------------
# Where the server and client write their activity logs (git-ignored; not game art).
SERVER_LOG = ASSETS_DIR.parent / "server.log"
CLIENT_LOG = ASSETS_DIR.parent / "client.log"

# --- Sound effects (played in reaction to bus events) ------------------------
# Effect names: the SoundEffects subscriber plays one of these per game event.
SOUND_MOVE = "move"
SOUND_CAPTURE = "capture"
SOUND_GAME_START = "game_start"
SOUND_GAME_OVER = "game_over"
# Winsound fallback tones per effect: (frequency in Hz, duration in ms). Used by
# WinsoundPlayer so the game makes sound with no audio-asset files.
WINSOUND_TONES = {
    SOUND_MOVE: (600, 60),
    SOUND_CAPTURE: (300, 120),
    SOUND_GAME_START: (880, 150),
    SOUND_GAME_OVER: (200, 400),
}
