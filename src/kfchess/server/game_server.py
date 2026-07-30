"""The WebSocket entry point: a thin async wrapper around the synchronous :class:`Lobby`.

All the behaviour — logging players in, matchmaking, routing moves, broadcasting — lives
in :class:`kfchess.server.lobby.Lobby`, which is fully unit-tested with fake ``send``
callbacks and no sockets. :func:`serve` is the irreducible async part: it accepts real
WebSocket connections, pumps outgoing messages through a per-connection queue, and ticks
the lobby on a timer. It only wires sockets to the hub, so it is excluded from coverage
like the cv2 I/O in ``img.py``.
"""

from __future__ import annotations


def next_sleep_s(hub, ceiling_ms: int) -> float:
    """How long the ticker may sleep before the lobby needs attention again.

    Until the soonest moment any game has scheduled — a piece arriving, a cooldown
    ending, a resign countdown reaching zero — but never longer than ``ceiling_ms``.

    The ceiling is what keeps the *periodic* duties on their own clock: the ten-second
    resync and the matchmaking timeouts count elapsed time rather than name a moment, so
    they need the loop to come round regularly whether or not a game has anything to do.
    Within that, this only ever pulls a wake-up *earlier*: a piece due in 10 ms is
    announced in 10 ms, instead of at whatever fixed boundary comes next.
    """
    due_ms = hub.next_event_delay_ms()
    return (ceiling_ms if due_ms is None else min(due_ms, ceiling_ms)) / 1000


async def serve(  # pragma: no cover  (irreducible async socket + timer I/O)
    new_board,
    host=None,
    port=None,
    tick_ms=None,
) -> None:
    """Run the WebSocket server until cancelled, driving one :class:`Lobby`.

    ``new_board`` makes a fresh starting board for each game the lobby spins up. Each
    connection gets an outgoing asyncio queue that a drain task feeds to the socket, so
    the synchronous hub can "send" by simply enqueuing. A background ticker advances all
    games and the matchmaking clock, waking on whichever comes first: the next event a
    game has scheduled, or ``tick_ms``. This is pure socket/timer plumbing around the
    tested hub, hence excluded from coverage — the two decisions it makes, how long to
    sleep and how much time has passed, are :func:`next_sleep_s` and a subtraction.
    """
    import asyncio
    import time

    import websockets

    from kfchess.config import (
        SERVER_HOST,
        SERVER_PORT,
        SERVER_TICK_MS,
        WS_PING_INTERVAL_S,
        WS_PING_TIMEOUT_S,
    )
    from kfchess.server.lobby import Lobby
    from kfchess.server.user_store import UserStore

    host = host or SERVER_HOST
    port = port or SERVER_PORT
    tick_ms = tick_ms or SERVER_TICK_MS
    hub = Lobby(new_board, UserStore())

    async def drain(queue: "asyncio.Queue", websocket) -> None:
        while True:
            await websocket.send(await queue.get())

    async def handler(websocket) -> None:
        queue: "asyncio.Queue" = asyncio.Queue()
        client_id = hub.connect(queue.put_nowait)
        sender = asyncio.create_task(drain(queue, websocket))
        try:
            async for text in websocket:
                hub.receive(client_id, text)
        finally:
            hub.disconnect(client_id)
            sender.cancel()

    async def ticker() -> None:
        # The game is advanced by the time that actually passed, not by the interval we
        # asked to sleep for: a loop that sleeps ~50 ms and always advances by exactly 50
        # falls further behind the wall clock the busier the server gets, and every
        # arrival time it hands out is wrong by the accumulated difference.
        last = time.monotonic()
        while True:
            await asyncio.sleep(next_sleep_s(hub, tick_ms))
            now = time.monotonic()
            hub.tick(round((now - last) * 1000))
            last = now

    async with websockets.serve(
        handler,
        host,
        port,
        # Keepalive so a silently dropped client is noticed (and its resign countdown
        # started) within ~20s, not the library's ~40s default.
        ping_interval=WS_PING_INTERVAL_S,
        ping_timeout=WS_PING_TIMEOUT_S,
    ):
        await ticker()
