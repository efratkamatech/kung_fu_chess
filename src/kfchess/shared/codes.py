"""The closed vocabularies both sides name: game phase, refusals, and lobby notices.

Where :mod:`kfchess.shared.protocol` defines the *shape* of each message, this defines
the small sets of values that travel inside them. Each was previously a bare string
literal written out at both ends — the server raising ``"illegal_move"`` and the client
comparing against ``"over"`` — which meant a typo was a silent no-op and the only list
of legal values was a comment.

Every enum subclasses ``str``, the same trick :class:`~kfchess.shared.protocol.MessageType`
uses: each member *is* its lowercase string, so ``json.dumps`` writes the plain tag, an
older comparison against a literal still holds, and the wire format is unchanged.

These live beside the protocol rather than inside it because the game layer needs them
too: :class:`~kfchess.server.session.GameSession` reports why it refused a move without
knowing that a wire, or a :class:`~kfchess.shared.protocol.Rejected` message, exists.
"""

from __future__ import annotations

from enum import Enum


class Phase(str, Enum):
    """The three phases a game moves through, as the banner and snapshot see it."""

    START = "start"      # a new game has begun; show the start overlay
    PLAYING = "playing"  # the first move has been made; no overlay
    OVER = "over"        # a king was captured; show the game-over overlay


class RejectReason(str, Enum):
    """Why the server refused something a client asked for.

    Carried by :class:`~kfchess.shared.protocol.Rejected`. The first two answer a
    connection-level request; the rest are the ways a move can be turned down, decided
    by the session against the live board.
    """

    BAD_PASSWORD = "bad_password"        # login: the account exists, the password is wrong
    NOT_A_PLAYER = "not_a_player"        # move: a spectator has no seat to move from
    GAME_OVER = "game_over"              # move: a king has already fallen
    # move: the command did not parse (bad length/letters, or a square off the board).
    # The parser's specific complaint stays server-side so the wire keeps to this
    # closed set; the Lobby logs the offending command next to this code.
    BAD_COMMAND = "bad_command"
    NOT_YOUR_COLOUR = "not_your_colour"  # move: the command names the other side
    EMPTY_SOURCE = "empty_source"        # move: no piece stands on the source square
    NOT_YOUR_PIECE = "not_your_piece"    # move: that piece belongs to the opponent
    WRONG_PIECE = "wrong_piece"          # move: the source holds a different piece type
    ILLEGAL_MOVE = "illegal_move"        # move: that piece cannot reach the target


class NoticeReason(str, Enum):
    """A lobby-level outcome that is neither game state nor a refused action.

    Carried by :class:`~kfchess.shared.protocol.Notice`: the client turns each into a
    message and offers the lobby menu again.
    """

    NO_OPPONENT = "no_opponent"    # the matchmaking search waited too long
    NO_SUCH_ROOM = "no_such_room"  # the id given to "join room" matches no open room
