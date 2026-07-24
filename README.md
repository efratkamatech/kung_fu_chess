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

**Networked multiplayer** — start the headless server, then one client per player.
The client asks for a username and password in the shell, then opens the window once
you are matched. Needs the `server` and `graphics` extras:

```bash
python server_main.py                          # listens on ws://localhost:8765
python client_main.py --url ws://localhost:8765
```

### Controls (windowed game & client)

- **Left-click** a piece to select it (a green outline marks it), then **left-click** a
  destination to move it there.
- **Right-click** a piece — or left-click an already-selected piece again — to **jump** in place.
- In the local windowed game, the game-over banner offers **[N]** new game or **[Esc]** quit.

## Layout

```
main.py  graphics_main.py  server_main.py  client_main.py   # the four entry points
src/kfchess/   # source, organized by layer (model, movement, rules, engine,
               # graphics, server, client, text_io, …)
tests/         # unit tests (mirror src) + text-fixture integration tests
docs/          # architecture.md and walkthroughs
```

## Tech

Python (standard library only at the core), `websockets` for the server, `opencv-python`
for rendering and input, and `sqlite3` (stdlib) for accounts and ratings. Sound in the
windowed game uses `winsound` and is Windows-only; the game runs without it elsewhere.

## Test

```bash
pytest                                   # run the suite
pytest --cov=kfchess --cov-report=html   # coverage + HTML report in htmlcov/
ruff check src tests                     # lint
```

CI runs `ruff` and the suite with a 100%-coverage gate on every push and pull request.
