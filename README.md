# Kung Fu Chess

[![CI](https://github.com/efratkamatech/kung_fu_chess/actions/workflows/ci.yml/badge.svg)](https://github.com/efratkamatech/kung_fu_chess/actions/workflows/ci.yml)

A real-time, **turn-less** chess variant in Python. Both sides move at once: every
piece moves independently, travels across the board over time (it does not teleport),
and enters a cooldown when it lands. Capturing the enemy king ends the game.

The same game core drives three front-ends — a text/stdin→stdout program, a windowed
single-machine game, and a networked multiplayer server + client — over one layered
backend (Model → Movement → RuleEngine → GameEngine → RealTimeArbiter → Controller).
The full design is written up in [docs/architecture.md](docs/architecture.md).

**Repository:** https://github.com/efratkamatech/kung_fu_chess.git

## Game mechanics

- **No turns.** Both players move simultaneously in real time.
- **Movement takes time.** A piece slides cell by cell from source to destination; it is
  vulnerable and cannot be re-moved until it arrives.
- **Cooldown.** After landing, a piece rests for a short cooldown before it can move again.
- **Collisions.** Two pieces that meet mid-path are resolved in true time order — a later
  arriver captures an enemy already there and continues, or stops one cell short of a friend.
- **Jump in place.** A piece can jump and stay airborne on its own cell for a moment
  (useful to dodge). An airborne piece captures an enemy that arrives under it.
- **Promotion.** A pawn reaching the far rank promotes to a queen.

The networked build adds accounts and password login (SQLite), ELO-based matchmaking,
private rooms with spectators, reconnection within a resign countdown, and sounds.

## Setup

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate      POSIX:  source .venv/bin/activate

# Pick the extras you need (the text core is pure standard library):
pip install -e ".[dev]"                    # core + tests
pip install -e ".[dev,graphics]"           # + the windowed game (OpenCV)
pip install -e ".[dev,server,graphics]"    # + the networked server & client
```

## Run

**Text core** — reads commands from stdin, writes the board to stdout (byte-exact, no prompts):

```bash
python main.py < path/to/fixture.in
```

**Windowed game** (one machine, both colours) — needs the `graphics` extra:

```bash
python graphics_main.py --white Alice --black Bob
```

**Networked multiplayer, on one machine** — one process, no infrastructure of any kind.
Start the server, then one client per player:

```bash
python server_main.py --solo
```

```bash
python client_main.py --url ws://localhost:8765
```

The client asks for a username and password in the shell, then opens the window once you
are matched. It needs the `graphics` extra; the server needs `server` (only `websockets`
is actually loaded in this mode). Accounts and ratings go to a local SQLite file.

**Networked multiplayer, split up** — the same server as several processes: a **gateway**
holding the WebSocket connections and a **shard** running the games, with NATS between
them, Redis for the state they share, and PostgreSQL for the accounts. Bring it up with
Docker and connect exactly the same clients:

```bash
docker compose up --build
```

Compose runs five services: `gateway` (the only one with a published port), `shard` (two
replicas), `nats`, `redis`, and `postgres`. The shards name themselves after their
containers, so neither is configured to know it is one of two — new games are spread
across whichever are alive, a game can be handed to either as it starts, and a room id
typed at one is answered by whichever is running it.

Accounts and ratings live in a named volume, so they survive `docker compose down`; Redis
deliberately has none, since everything in it expires in minutes anyway. To run the pieces by hand instead you need NATS and Redis
(`NATS_URL`, `REDIS_URL`), then `python server_main.py` and `python gateway_main.py`.

**The two are the same game.** Not a cut-down local build and a real one: the same
gateway holds the sockets, the same shard runs the games, and the same lobby decides
everything either is asked. Two objects underneath them differ — the bus between gateway
and shard, and the store the shared state lives in — and both are chosen in one line, in
`server/solo.py` and `shard.serve`. Nothing above that line can tell which it got, and
the client never could: it opens one WebSocket either way.

### Controls (windowed game & client)

- **Left-click** a piece to select it (a green outline marks it), then **left-click** a
  destination to move it there.
- **Right-click** a piece — or left-click an already-selected piece again — to **jump** in place.
- In the local windowed game, the game-over banner offers **[N]** new game or **[Esc]** quit.

## Layout

```
main.py  graphics_main.py  client_main.py                     # text, windowed, client
server_main.py  gateway_main.py                              # the shard and a gateway
src/kfchess/   # source, organized by layer (model, movement, rules, engine,
               # server, gateway, client, graphics, text_io, bus/ — the event
               # and message buses, and shared/ — the wire vocabulary the
               # server and client both speak)
tests/         # unit tests (mirror src) + text-fixture integration tests
docs/          # architecture.md and walkthroughs
migrations/    # the PostgreSQL schema, applied on the database's first boot
Dockerfile  docker-compose.yml                              # the containerised server
```

## Tech

Python (standard library only at the core), `websockets` for the gateway, `nats-py`
between the services, `redis` for the state they share, `opencv-python`
for rendering and input, and `sqlite3` (stdlib) — or PostgreSQL via `psycopg`, under
Docker — for accounts and ratings. Sound in the windowed game uses `winsound` and is
Windows-only; the game runs without it elsewhere.

## Test

```bash
pytest                                   # run the suite
pytest --cov=kfchess --cov-report=html   # coverage + HTML report in htmlcov/
ruff check src tests                     # lint
```

CI runs `ruff` and the suite with a 100%-coverage gate on every push and pull request.
