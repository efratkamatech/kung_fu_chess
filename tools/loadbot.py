"""A crowd of headless players, to find out whether the design's numbers were right.

Every capacity figure in ``Server_Design_EN.md`` was reasoned to, not measured. This
opens as many real WebSocket connections as you ask for, logs each one in, gets them
matched into games, and has them play — then reports what it saw, whatever that is.

    python tools/loadbot.py --connections 200 --seconds 60
    python tools/loadbot.py --connections 1000 --url ws://localhost:8765

Three numbers come out, and they line up with the three claims:

- **bytes per second per connection**, against ~325 B/s (~2.6 kbps). Measured on the
  receiving side, which is the side the claim is about.
- **move latency percentiles**, against "a move should be felt in well under 100 ms".
  Measured end to end, from writing the command to reading the delta it caused — the two
  network hops the server cannot see itself.
- **how many games one server sustains** before those percentiles come apart.

It moves a **knight back and forth** (b1→c3→b1), which is the one piece that can return
to where it started for ever. That keeps every move legal without the bot having to model
the board at all: no engine, no snapshot rebuilding, nothing that could make the load
generator itself the slow part.

It needs `websockets` and nothing else — no OpenCV, no game code. A load bot that
imported the client would be measuring the client.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import string
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kfchess.obs.metrics import (  # noqa: E402  (after the path is set up)
    LATENCY_BUCKETS_MS,
    SIZE_BUCKETS_B,
    Registry,
)

# The two squares a knight shuttles between, per colour. Nothing else on the board ever
# moves, so neither square is ever occupied by anything but this knight.
SHUTTLE = {
    "w": ("Nb1c3", "Nc3b1"),
    "b": ("Nb8c6", "Nc6b8"),
}

MEASURES = Registry()
LATENCY_MS = MEASURES.histogram(
    "loadbot_move_latency_ms",
    "Milliseconds from writing a move to reading the delta it caused.",
    buckets=LATENCY_BUCKETS_MS,
)
BYTES_PER_CONN = MEASURES.histogram(
    "loadbot_bytes_per_conn",
    "Bytes received by one connection over the whole run.",
    buckets=SIZE_BUCKETS_B,
)


class Bot:
    """One player: a socket, a colour, and a knight it moves back and forth."""

    def __init__(self, url: str, name: str, move_every_s: float) -> None:
        self.url = url
        self.name = name
        self.move_every_s = move_every_s
        self.color = None
        self.bytes_in = 0
        self.moves = 0
        self.refused = 0
        self._shuttle = 0

    async def play(self, until: float) -> None:
        """Log in, get a game, and keep playing until ``until`` (a monotonic deadline)."""
        import websockets

        async with websockets.connect(self.url, ping_interval=None) as socket:
            await self._say(socket, {"type": "login", "username": self.name, "password": "x"})
            await self._wait_for(socket, {"welcome"}, until)
            await self._say(socket, {"type": "play"})
            seated = await self._wait_for(socket, {"seated"}, until)
            if seated is None:
                return  # never matched: the run ended, or nobody was left to pair with
            self.color = seated["color"]
            if self.color is None:
                return  # a spectator has nothing to contribute to a load test
            await self._shuttle_until(socket, until)

    async def _shuttle_until(self, socket, until: float) -> None:
        """Move, wait for the piece to be free again, pause, repeat.

        Waiting for the cooldown rather than trusting a fixed interval is the difference
        between measuring the server and measuring the bot: a piece is in flight for a
        second per cell and rests for another, so a timer set below that produces a
        stream of refusals and a latency figure drawn from the few that got through.
        """
        while time.monotonic() < until:
            command = self.color.upper() + SHUTTLE[self.color][self._shuttle % 2]
            started = time.perf_counter()
            await self._say(socket, {"type": "move", "cmd": command})
            answered = await self._wait_for(socket, {"move_started", "rejected"}, until)
            if answered is None:
                return
            if answered["type"] == "rejected":
                self.refused += 1
                await asyncio.sleep(self.move_every_s)  # back off rather than spin
                continue
            LATENCY_MS.observe((time.perf_counter() - started) * 1000)
            self.moves += 1
            self._shuttle += 1
            # It is airborne now, and then resting. Asking again before it lands would be
            # asking for a refusal.
            free = await self._wait_for(
                socket, {"cooldown_done"}, until, lambda m: m["piece_id"] == answered["piece_id"]
            )
            if free is None:
                return
            await asyncio.sleep(self.move_every_s)

    async def _say(self, socket, message: dict) -> None:
        await socket.send(json.dumps(message))

    async def _wait_for(self, socket, kinds, until: float, matching=None):
        """Read until one of ``kinds`` arrives, weighing everything that goes past.

        Everything is weighed, not just what was waited for: the bytes claim is about
        what a connection *receives*, and most of that is other people's deltas and the
        periodic resync — exactly the traffic a bot only waiting for its own answer
        would forget to count.

        ``matching`` narrows it further, because a room's deltas are everybody's: a
        cooldown ending is not this bot's cooldown ending unless it names its piece.
        """
        while True:
            remaining = until - time.monotonic()
            if remaining <= 0:
                return None
            try:
                raw = await asyncio.wait_for(socket.recv(), timeout=remaining)
            except Exception:
                return None  # the deadline, or the socket closing: either ends this bot
            self.bytes_in += len(raw)
            message = json.loads(raw)
            if message["type"] in kinds and (matching is None or matching(message)):
                return message


async def run(url: str, connections: int, seconds: float, move_every_s: float) -> None:
    """Open ``connections`` bots, play for ``seconds``, and report what happened."""
    suffix = "".join(random.choices(string.ascii_lowercase, k=6))
    bots = [Bot(url, f"bot-{suffix}-{index}", move_every_s) for index in range(connections)]
    until = time.monotonic() + seconds

    print(f"opening {connections} connections to {url} for {seconds:g}s...")
    started = time.monotonic()
    await asyncio.gather(*(bot.play(until) for bot in bots), return_exceptions=True)
    elapsed = time.monotonic() - started

    _report(bots, elapsed)


def _report(bots, elapsed: float) -> None:
    playing = [bot for bot in bots if bot.color is not None]
    moves = sum(bot.moves for bot in playing)
    refused = sum(bot.refused for bot in playing)
    total_bytes = sum(bot.bytes_in for bot in bots)
    for bot in bots:
        BYTES_PER_CONN.observe(bot.bytes_in)

    per_conn_per_s = total_bytes / len(bots) / elapsed if bots and elapsed else 0

    print(f"\n{'ran for':<28}{elapsed:.1f}s")
    print(f"{'connections':<28}{len(bots)}")
    print(f"{'seated in a game':<28}{len(playing)}")
    print(f"{'games':<28}{len(playing) // 2}")
    print(f"{'moves played':<28}{moves}   ({refused} refused)")
    print(f"{'moves per second':<28}{moves / elapsed:.1f}" if elapsed else "")
    print("\nmove latency, end to end")
    for fraction in (0.5, 0.9, 0.99):
        print(f"{'  p' + str(int(fraction * 100)):<28}<= {LATENCY_MS.percentile(fraction):g} ms")
    print(f"{'  mean':<28}{LATENCY_MS.average:.1f} ms")
    print("\nbytes received")
    print(f"{'  per connection':<28}{total_bytes / len(bots):,.0f} B" if bots else "")
    print(f"{'  per connection per second':<28}{per_conn_per_s:,.0f} B/s"
          f"   ({per_conn_per_s * 8 / 1000:.1f} kbps)")
    print("\nthe claims this is measured against")
    print(f"{'  design: bytes/s/conn':<28}~325 B/s (2.6 kbps)")
    print(f"{'  design: move felt within':<28}100 ms")


def main() -> None:
    parser = argparse.ArgumentParser(description="Load-test the KungFu Chess server.")
    parser.add_argument("--url", default="ws://localhost:8765", help="the gateway to open")
    parser.add_argument("--connections", type=int, default=100, help="how many players")
    parser.add_argument("--seconds", type=float, default=30, help="how long to play for")
    parser.add_argument(
        "--move-every", type=float, default=2.0, help="seconds between one bot's moves"
    )
    args = parser.parse_args()
    asyncio.run(run(args.url, args.connections, args.seconds, args.move_every))


if __name__ == "__main__":
    main()
