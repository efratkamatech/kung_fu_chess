"""The WebSocket entry point: a thin async wrapper around the synchronous :class:`Lobby`.

All the behaviour — logging players in, matchmaking, routing moves, broadcasting — lives
in :class:`kfchess.server.lobby.Lobby`, which is fully unit-tested with fake ``send``
callbacks and no sockets. :func:`serve` is the irreducible async part: it accepts real
WebSocket connections, pumps outgoing messages through a per-connection queue, and ticks
the lobby on a timer. It only wires sockets to the hub, so it is excluded from coverage
like the cv2 I/O in ``img.py``.
"""

from __future__ import annotations


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
    games and the matchmaking clock on a fixed interval. This is pure socket/timer
    plumbing around the tested hub, hence excluded from coverage.
    """
    import asyncio

    import websockets

    from kfchess.config import SERVER_HOST, SERVER_PORT, SERVER_TICK_MS
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
        while True:
            await asyncio.sleep(tick_ms / 1000)
            hub.tick(tick_ms)

    async with websockets.serve(handler, host, port):
        await ticker()
