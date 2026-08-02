"""The six numbers, in one place, each named for the claim it exists to settle.

Declared together rather than at their call sites so that what this server publishes can
be read in one screen — and so that the connection between a measurement and the sentence
in the design it is checking does not live only in somebody's memory.

| Measure | Claim in ``Server_Design_EN.md`` |
|---|---|
| ``kfc_active_games`` | ~500 games to a shard |
| ``kfc_connections`` | ~30,000 sockets to a gateway |
| ``kfc_game_tick_us`` | a tick resolves in ~50 µs |
| ``kfc_move_handling_ms`` | the server's share of a move being felt |
| ``kfc_bytes_out_total`` | ~325 B/s to a player (~2.6 kbps) |
| ``kfc_matches_total`` | the matchmaker, not the engine, is the hot path |
| ``kfc_logins_total`` / ``kfc_login_ms`` | that moving the password check off the game thread raised admissions |

Two of these are named differently from the implementation plan, and deliberately.

``kfc_game_tick_us`` was to be ``kfc_resolve_duration_us``. It is measured around a whole
game's tick rather than around ``resolve()`` alone, because the core may not import this
package — the engine has never imported anything above it and this is not the reason to
start. What it measures is a superset of the assumption and the better number anyway:
what one game costs per tick is what decides how many fit on a shard.

``kfc_bytes_out_total`` was to be a histogram of bytes per connection. It is a counter,
because "bytes per second per connection" is a *rate* over a *gauge*, and both parts are
here — a scraper divides them. A histogram would have measured the size of individual
messages, which is not the claim.
"""

from __future__ import annotations

from kfchess.obs.metrics import (
    DURATION_BUCKETS_US,
    LATENCY_BUCKETS_MS,
    REGISTRY,
)

# --- what a shard is doing -----------------------------------------------------

ACTIVE_GAMES = REGISTRY.gauge(
    "kfc_active_games",
    "Games this shard is currently running.",
)

GAME_TICK_US = REGISTRY.histogram(
    "kfc_game_tick_us",
    "Microseconds to advance one game by one tick, resolve() included.",
    buckets=DURATION_BUCKETS_US,
)

MOVE_HANDLING_MS = REGISTRY.histogram(
    "kfc_move_handling_ms",
    "Milliseconds from a move reaching the shard to its delta being published.",
    buckets=LATENCY_BUCKETS_MS,
)

MATCHES = REGISTRY.counter(
    "kfc_matches_total",
    "Pairs of players matched into a game since this shard started.",
)

# --- what the auth service is doing --------------------------------------------

LOGINS = REGISTRY.counter(
    "kfc_logins_total",
    "Passwords checked since this service started, accepted or not.",
)

LOGIN_MS = REGISTRY.histogram(
    "kfc_login_ms",
    "Milliseconds to check one password. Nearly all of it is PBKDF2, by design.",
    buckets=LATENCY_BUCKETS_MS,
)

# --- what a gateway is doing ---------------------------------------------------

CONNECTIONS = REGISTRY.gauge(
    "kfc_connections",
    "Sockets this gateway is currently holding.",
)

BYTES_OUT = REGISTRY.counter(
    "kfc_bytes_out_total",
    "Bytes written towards players since this gateway started.",
)
