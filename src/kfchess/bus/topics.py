"""Topic names for the pub/sub :class:`EventBus` — the "channels" events travel on.

A publisher announces an event on a topic; a subscriber listens to a topic. Keeping
the names here as constants (never inline strings) means a publisher and its
subscribers always agree on the exact channel, and a rename is a one-line change —
the same config-not-constants rule the text/wire format follows in ``config.py``.

The four game events below are the *sources* everything else reacts to: the scoreboard
and moves log listen for ``CAPTURE``/``MOVE_STARTED``, sound listens to all of them,
and the start/end animations listen for ``GAME_STARTED``/``GAME_OVER``.
"""

MOVE_STARTED = "move_started"  # a piece began moving (payload: MoveStarted)
CAPTURE = "capture"            # a piece was captured (payload: Captured)
GAME_STARTED = "game_started"  # a new game has begun (payload: GameStarted)
GAME_OVER = "game_over"        # a king was captured; the game ended (payload: GameOver)
